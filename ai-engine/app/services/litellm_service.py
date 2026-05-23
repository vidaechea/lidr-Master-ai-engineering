from __future__ import annotations

import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import TypeVar

import instructor
import litellm
import structlog
from litellm import Router
from pydantic import BaseModel as PydanticBaseModel

from app.config import LOGICAL_MODEL, _FALLBACK_MODEL, MODEL_REGISTRY, build_model_list, settings
from app.schemas.llm import LLMObservableResponse
from app.services.helpers.error_mapper import LLMServiceError
from app.services.helpers.llm_observable_builder import LLMObservableResponseBuilder

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
        self._observable_builder = LLMObservableResponseBuilder()
        log.info(
            "litellm_router_service_created",
            logical_model=LOGICAL_MODEL,
            primary_model=self._primary_model,
            fallback_model=self._fallback_model,
        )

    def _calculate_cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate cost in USD from token counts and MODEL_REGISTRY pricing.
        
        Formula: (input_tokens × input_price + output_tokens × output_price) / 1,000,000
        
        Handles model name normalization:
          - Strips provider prefix (e.g., "anthropic/claude-haiku" → "claude-haiku")
          - Strips version suffix (e.g., "gpt-4o-mini-2024-07-18" → "gpt-4o-mini")
        
        Args:
            model: Model name (e.g., 'gpt-4o-mini', 'gpt-4o-mini-2024-07-18', 'anthropic/claude-haiku-...')
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens generated.
        
        Returns:
            Cost in USD as Decimal. Returns Decimal('0') if model not in registry.
        """
        import re
        
        # Normalize model name (strip provider prefix if present)
        normalized_model = model.split('/', 1)[1] if '/' in model else model
        
        # Try exact match first
        if normalized_model in MODEL_REGISTRY:
            config = MODEL_REGISTRY[normalized_model]
            cost = (
                input_tokens * config.input_price +
                output_tokens * config.output_price
            ) / 1_000_000
            return Decimal(str(cost))
        
        # Try to find base model by stripping version suffix (e.g., gpt-4o-mini-2024-07-18 → gpt-4o-mini)
        # Look for pattern like "-YYYY-MM-DD" or "-YYYYMMDD" at the end
        match = re.match(r'^(.+?)-(?:\d{4}-\d{2}-\d{2}|\d{8})$', normalized_model)
        if match:
            base_model = match.group(1)
            if base_model in MODEL_REGISTRY:
                config = MODEL_REGISTRY[base_model]
                cost = (
                    input_tokens * config.input_price +
                    output_tokens * config.output_price
                ) / 1_000_000
                log.info(
                    "cost_calculated_with_base_model",
                    model=model,
                    base_model=base_model,
                    cost=cost,
                )
                return Decimal(str(cost))
        
        # Model not found in registry
        log.warning(
            "model_not_in_registry_cost_zero",
            model=model,
            normalized=normalized_model,
        )
        return Decimal('0')

    async def complete(self, messages: list[dict], **kwargs) -> LLMObservableResponse:
        """Execute a non-streaming completion and return observable response.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional arguments passed to the router.

        Returns:
            LLMObservableResponse with model, usage, latency_ms, and cost_usd.

        Raises:
            LLMServiceError: On provider errors or other failures.
        """
        start_time = time.perf_counter()
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

        content = response.choices[0].message.content if response.choices else None
        response_id = getattr(response, "id", None)
        usage = getattr(response, "usage", None)

        # Calculate cost from token counts and MODEL_REGISTRY pricing
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        cost_usd = self._calculate_cost_usd(actual_model or LOGICAL_MODEL, input_tokens, output_tokens)

        return self._observable_builder.build_from_timer(
            model=actual_model or LOGICAL_MODEL,
            usage=usage,
            start_time=start_time,
            content=content,
            response_id=response_id,
            raw_response=response,
            cost_usd=cost_usd,
        )

    async def stream(
        self,
        messages: list[dict],
        usage_out: list | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Yield text deltas from a streaming LLM call.

        When *usage_out* is provided, an LLMObservableResponse is appended to the list
        after the last delta is yielded, containing complete usage and cost metrics.
        """
        if usage_out is not None:
            kwargs.setdefault("stream_options", {"include_usage": True})
        start_time = time.perf_counter()
        try:
            response = await self._router.acompletion(
                model=LOGICAL_MODEL,
                messages=messages,
                stream=True,
                **kwargs,
            )
            response_id: str | None = None
            last_usage = None
            actual_model = None
            async for chunk in response:
                if response_id is None:
                    response_id = getattr(chunk, "id", None)
                if actual_model is None:
                    actual_model = getattr(chunk, "model", None) or LOGICAL_MODEL
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    last_usage = chunk_usage
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
            if usage_out is not None and last_usage is not None:
                # Calculate cost from token counts
                input_tokens = getattr(last_usage, "prompt_tokens", 0)
                output_tokens = getattr(last_usage, "completion_tokens", 0)
                cost_usd = self._calculate_cost_usd(actual_model or LOGICAL_MODEL, input_tokens, output_tokens)
                
                observable_resp = self._observable_builder.build_from_timer(
                    model=actual_model or LOGICAL_MODEL,
                    usage=last_usage,
                    start_time=start_time,
                    response_id=response_id,
                    cost_usd=cost_usd,
                )
                usage_out.append(observable_resp)
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
    ) -> tuple[T, LLMObservableResponse]:
        """Call the router with instructor to get a structured Pydantic response.

        Returns a ``(instance, observable_response)`` tuple so callers can access
        the structured output and observability metrics in one call.

        Args:
            messages: List of message dicts.
            response_model: Pydantic model class for structured output.
            max_retries: Maximum number of retries by instructor.
            **kwargs: Additional arguments passed to the router.

        Returns:
            Tuple of (parsed_instance, LLMObservableResponse).

        Raises:
            LLMServiceError: On provider errors or structural validation failures.
        """
        start_time = time.perf_counter()
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

        usage = getattr(completion, "usage", None)
        response_id = getattr(completion, "id", None)

        # Calculate cost from token counts and MODEL_REGISTRY pricing
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        cost_usd = self._calculate_cost_usd(actual_model or LOGICAL_MODEL, input_tokens, output_tokens)

        observable_response = self._observable_builder.build_from_timer(
            model=actual_model or LOGICAL_MODEL,
            usage=usage,
            start_time=start_time,
            response_id=response_id,
            raw_response=completion,
            cost_usd=cost_usd,
        )

        return result, observable_response


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
