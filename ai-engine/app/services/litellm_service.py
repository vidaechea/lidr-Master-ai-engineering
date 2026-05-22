from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TypeVar

import instructor
import litellm
import structlog
from litellm import Router
from pydantic import BaseModel as PydanticBaseModel

from app.config import LOGICAL_MODEL, _FALLBACK_MODEL, build_model_list, settings
from app.services.helpers.error_mapper import LLMServiceError

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=PydanticBaseModel)

_LITELLM_ERROR_MAP: dict[type[Exception], tuple[str, int]] = {
    litellm.AuthenticationError: ("authentication_error", 401),
    litellm.RateLimitError: ("rate_limit_error", 429),
    litellm.BadRequestError: ("bad_request_error", 400),
    litellm.ContextWindowExceededError: ("context_window_exceeded", 413),
    litellm.NotFoundError: ("model_not_found", 404),
    litellm.APIConnectionError: ("connection_error", 503),
    litellm.ServiceUnavailableError: ("service_unavailable", 503),
    litellm.Timeout: ("timeout", 504),
    litellm.InternalServerError: ("internal_server_error", 502),
}


class LiteLLMRouterService:
    """LLM service backed by a litellm Router with primary + fallback models.

    Failover policy:
      1. Primary model (OpenAI gpt-4o-mini) is always tried first.
      2. After ``router_num_retries`` failures the Router falls back to
         Anthropic claude-haiku via the ``fallbacks`` list.
      3. ``timeout`` caps each provider call.
      4. ``retry_after`` adds back-off on 429s.
      5. ``allowed_fails`` / ``cooldown_time`` implement a circuit-breaker.
    """

    def __init__(
        self,
        primary_model: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        _model_list = build_model_list(primary_model, fallback_model)
        self._router = Router(
            model_list=_model_list,
            fallbacks=[{LOGICAL_MODEL: [_FALLBACK_MODEL]}],
            num_retries=settings.router_num_retries,
            timeout=settings.router_timeout,
            retry_after=settings.router_retry_after,
            allowed_fails=settings.router_allowed_fails,
            cooldown_time=settings.router_cooldown_time,
        )
        self._primary_model = _model_list[0]["litellm_params"]["model"]
        self._fallback_model = _model_list[1]["litellm_params"]["model"]
        log.info(
            "litellm_router_service_created",
            logical_model=LOGICAL_MODEL,
            primary_model=self._primary_model,
            fallback_model=self._fallback_model,
        )

    async def complete(self, messages: list[dict], **kwargs):
        try:
            response = await self._router.acompletion(
                model=LOGICAL_MODEL,
                messages=messages,
                **kwargs,
            )
        except tuple(_LITELLM_ERROR_MAP) as exc:
            error_type, status_code = _LITELLM_ERROR_MAP[type(exc)]
            log.error(
                "router_provider_failed",
                error_type=error_type,
                failed_provider=getattr(exc, "llm_provider", "unknown"),
                failed_model=getattr(exc, "model", "unknown"),
                fallback_exhausted=True,
            )
            raise LLMServiceError(error_type, str(exc), status_code) from exc

        actual_model = getattr(response, "model", "") or ""
        if actual_model and "gpt-4o-mini" not in actual_model:
            log.warning(
                "router_fallback_used",
                requested_model="gpt-4o-mini",
                actual_model=actual_model,
            )

        return response

    async def stream(
        self,
        messages: list[dict],
        usage_out: list | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Yield text deltas from a streaming LLM call.

        When *usage_out* is provided the final chunk's usage statistics and
        response ID are appended to the list after the last delta is yielded,
        enabling callers to build cost/token metadata without a second call.
        """
        if usage_out is not None:
            kwargs.setdefault("stream_options", {"include_usage": True})
        try:
            response = await self._router.acompletion(
                model=LOGICAL_MODEL,
                messages=messages,
                stream=True,
                **kwargs,
            )
            response_id: str | None = None
            last_usage = None
            async for chunk in response:
                if response_id is None:
                    response_id = getattr(chunk, "id", None)
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    last_usage = chunk_usage
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
            if usage_out is not None:
                usage_out.append({"usage": last_usage, "response_id": response_id})
        except tuple(_LITELLM_ERROR_MAP) as exc:
            error_type, status_code = _LITELLM_ERROR_MAP[type(exc)]
            log.error(
                "router_stream_failed",
                error_type=error_type,
                failed_provider=getattr(exc, "llm_provider", "unknown"),
                failed_model=getattr(exc, "model", "unknown"),
            )
            raise LLMServiceError(error_type, str(exc), status_code) from exc

    async def complete_structured(
        self,
        messages: list[dict],
        response_model: type[T],
        max_retries: int = 3,
        **kwargs,
    ) -> tuple[T, object]:
        """Call the router with instructor to get a structured Pydantic response.

        Returns a ``(instance, raw_completion)`` tuple so callers can access
        token usage and other metadata from the underlying litellm response.
        """
        client = instructor.from_litellm(self._router.acompletion)
        try:
            result, completion = await client.chat.completions.create_with_completion(
                model=LOGICAL_MODEL,
                messages=messages,
                response_model=response_model,
                max_retries=max_retries,
                **kwargs,
            )
        except instructor.exceptions.InstructorRetryException as exc:
            log.error(
                "instructor_max_retries_exceeded",
                response_model=response_model.__name__,
                max_retries=max_retries,
            )
            raise LLMServiceError(
                "structured_output_failed",
                f"Model failed to produce valid {response_model.__name__} after {max_retries} retries: {exc}",
                422,
            ) from exc
        except tuple(_LITELLM_ERROR_MAP) as exc:
            error_type, status_code = _LITELLM_ERROR_MAP[type(exc)]
            log.error(
                "router_structured_failed",
                error_type=error_type,
                response_model=response_model.__name__,
                failed_provider=getattr(exc, "llm_provider", "unknown"),
            )
            raise LLMServiceError(error_type, str(exc), status_code) from exc

        actual_model = getattr(completion, "model", "") or ""
        if actual_model and self._primary_model not in actual_model:
            log.warning(
                "router_structured_fallback_used",
                requested_model=self._primary_model,
                actual_model=actual_model,
            )

        return result, completion


# Module-level singleton — one Router instance shared across all requests.
litellm_router_service = LiteLLMRouterService()


def create_litellm_router_service(
    primary_model: str | None = None,
    fallback_model: str | None = None,
) -> LiteLLMRouterService:
    """Factory that creates (and replaces) the module-level singleton.

    Call this from the Streamlit UI whenever the user changes the primary or
    fallback model so that subsequent requests use the new configuration.
    """
    global litellm_router_service  # noqa: PLW0603
    litellm_router_service = LiteLLMRouterService(primary_model, fallback_model)
    return litellm_router_service
