"""LiteLLM Router service — provider-transparent LLM wrapper.

Failover policy (ordered, not random):
  1. All calls are sent to the primary model (``LOGICAL_MODEL`` → OpenAI gpt-4o-mini).
  2. If it fails after ``num_retries`` attempts the Router automatically retries
     on the fallback model (``_FALLBACK_MODEL`` → Anthropic claude-haiku) via the
     ``fallbacks`` list — guaranteeing OpenAI-first, Anthropic-second ordering.
  3. ``timeout`` caps each individual provider call so we never wait forever.
  4. ``retry_after`` adds a back-off delay before retrying a 429 / rate-limit.
  5. ``allowed_fails`` / ``cooldown_time`` implement a circuit-breaker: once a
     model accumulates too many consecutive failures it is marked unhealthy and
     skipped for ``cooldown_time`` seconds before being reconsidered.
"""
from collections.abc import AsyncIterator
from typing import Any, Optional

import litellm
import structlog
import tiktoken
from litellm import Router

from app.config import settings
from app.services.llm.base import BaseLLMService, LLMServiceError, ModelInfo, ParsedResponse
from app.services.helpers.error_mapper import ErrorMapper
from app.services.helpers.token_counter import TokenCounter

log = structlog.get_logger(__name__)

# Primary logical name used by all callers — maps to OpenAI gpt-4o-mini.
LOGICAL_MODEL = "estimator"
# Fallback logical name — maps to Anthropic claude-haiku; never called directly.
_FALLBACK_MODEL = "estimator-fb"

# Pricing baseline: gpt-4o-mini (primary model).
# Cost is an approximation; the router may transparently use Anthropic on fallback.
_MODEL_INFO = ModelInfo(
    input_price=0.15,
    output_price=0.60,
    context_window=128_000,
    reasoning=False,
)


# --------------------------------------------------------------------------- #
# LiteLLM token counter
# --------------------------------------------------------------------------- #
class LiteLLMTokenCounter(TokenCounter):
    """Token counter for LiteLLM (uses tiktoken for the primary model)."""

    def count_tokens(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
    ) -> int:
        """Count tokens using tiktoken (OpenAI gpt-4o-mini encoding).
        
        Since LiteLLM may transparently fall back to Anthropic, we use
        OpenAI's encoding as a conservative estimate.
        """
        encoding = tiktoken.get_encoding("o200k_base")
        tokens = 0
        for text in (system_prompt, user_message):
            tokens += len(encoding.encode(text))
        # Add message overhead and priming tokens (OpenAI convention)
        tokens += 6
        return tokens


class LiteLLMRouterService(BaseLLMService):
    """LLM service backed by ``litellm.Router`` with automatic provider fallback.

    Two backend models share the logical name ``LOGICAL_MODEL``. litellm
    load-balances between them and retries on failure, so the application layer
    is fully decoupled from the underlying provider choice.
    """

    _LITELLM_ERROR_MAPPING = {
        **ErrorMapper.build_provider_error_mapping(
            provider_label="LiteLLM",
            auth_error_type=litellm.AuthenticationError,
            rate_limit_type=litellm.RateLimitError,
            bad_request_type=litellm.BadRequestError,
            connection_type=litellm.APIConnectionError,
            internal_error_type=litellm.InternalServerError,
        )
    }

    def __init__(self) -> None:
        super().__init__()
        self._router = Router(
            model_list=[
                {
                    # Primary: OpenAI gpt-4o-mini — always tried first.
                    "model_name": LOGICAL_MODEL,
                    "litellm_params": {
                        "model": "gpt-4o-mini",
                        "api_key": settings.openai_api_key,
                    },
                },
                {
                    # Fallback: Anthropic claude-haiku — only used when primary exhausts retries.
                    "model_name": _FALLBACK_MODEL,
                    "litellm_params": {
                        "model": "anthropic/claude-haiku-4-5-20251001",
                        "api_key": settings.anthropic_api_key,
                    },
                },
            ],
            # Ordered failover: primary → fallback (never random shuffle).
            fallbacks=[{LOGICAL_MODEL: [_FALLBACK_MODEL]}],
            # Retry the *same* model up to 2 times before triggering the fallback.
            num_retries=settings.router_num_retries,
            # Hard cap per provider call — prevents hanging on slow responses.
            timeout=settings.router_timeout,
            # Back-off (seconds) before retrying after a 429 / rate-limit error.
            retry_after=settings.router_retry_after,
            # Circuit-breaker: mark a model unhealthy after this many consecutive failures …
            allowed_fails=settings.router_allowed_fails,
            # … and keep it out of rotation for this many seconds.
            cooldown_time=settings.router_cooldown_time,
        )
        log.info(
            "litellm_router_service_created",
            logical_model=LOGICAL_MODEL,
            fallback_model=_FALLBACK_MODEL,
        )

    # ---------------------------------------------------------------------- #
    # Abstract method implementations
    # ---------------------------------------------------------------------- #

    @property
    def _provider_name(self) -> str:
        return "openai"  # primary intended provider

    def _get_model_info(self, model: str | None) -> tuple[str, ModelInfo]:
        if model is not None:
            raise ValueError(
                f"LiteLLMRouterService does not accept a model override (got {model!r}). "
                "Provider selection is managed by the router."
            )
        return LOGICAL_MODEL, _MODEL_INFO

    def _create_token_counter(self) -> TokenCounter:
        """Create a token counter for LiteLLM."""
        return LiteLLMTokenCounter()

    def _build_api_params(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        transcription: str,
        model_info: ModelInfo,
        temperature: Optional[float],
        top_p: Optional[float],
        top_k: Optional[int],
        reasoning_effort: str,
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcription},
            ],
            "max_tokens": max_output_tokens,
        }
        if temperature is not None:
            params["temperature"] = temperature
        elif top_p is not None:
            params["top_p"] = top_p
        if top_k is not None:
            params["top_k"] = top_k
        return params

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        try:
            return await self._router.acompletion(**api_params)
        except (
            litellm.AuthenticationError,
            litellm.RateLimitError,
            litellm.BadRequestError,
            litellm.APIConnectionError,
            litellm.InternalServerError,
        ) as exc:
            log.error(
                "router_provider_failed",
                error_type=type(exc).__name__,
                failed_provider=getattr(exc, "llm_provider", "unknown"),
                failed_model=getattr(exc, "model", api_params.get("model", "unknown")),
                fallback_configured=True,
                fallback_exhausted=True,
                max_retries=settings.router_num_retries,
            )
            ErrorMapper.map_exception(exc, self._LITELLM_ERROR_MAPPING)

    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> ParsedResponse:
        actual_model = getattr(response, "model", "") or ""
        fallback_provider: str | None = None
        if actual_model and "gpt-4o-mini" not in actual_model:
            if "anthropic" in actual_model or "claude" in actual_model:
                fallback_provider = "anthropic"
            else:
                fallback_provider = actual_model
        if fallback_provider:
            log.warning(
                "router_fallback_used",
                requested_model="gpt-4o-mini",
                actual_model=actual_model,
                fallback_provider=fallback_provider,
            )
        return ParsedResponse(
            estimation=response.choices[0].message.content,
            response_id=response.id,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            reasoning_tokens=None,
            finish_reason=response.choices[0].finish_reason or "stop",
            fallback_provider=fallback_provider,
        )

    async def _call_provider_stream(
        self,
        api_params: dict[str, Any],
        *,
        is_reasoning: bool,
    ) -> AsyncIterator[str]:
        params = {**api_params, "stream": True, "stream_options": {"include_usage": True}}
        usage_data = None
        last_id = "unknown"
        actual_model: str = ""

        try:
            response = await self._router.acompletion(**params)
            async for chunk in response:
                last_id = getattr(chunk, "id", last_id)
                if not actual_model:
                    actual_model = getattr(chunk, "model", "") or ""
                if getattr(chunk, "usage", None) is not None:
                    usage_data = chunk.usage
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except LLMServiceError:
            raise
        except (
            litellm.AuthenticationError,
            litellm.RateLimitError,
            litellm.BadRequestError,
            litellm.APIConnectionError,
            litellm.InternalServerError,
        ) as exc:
            log.error(
                "router_provider_failed",
                error_type=type(exc).__name__,
                failed_provider=getattr(exc, "llm_provider", "unknown"),
                failed_model=getattr(exc, "model", api_params.get("model", "unknown")),
                fallback_configured=True,
                fallback_exhausted=True,
                max_retries=settings.router_num_retries,
            )
            ErrorMapper.map_exception(exc, self._LITELLM_ERROR_MAPPING)

        fallback_provider: str | None = None
        if actual_model and "gpt-4o-mini" not in actual_model:
            if "anthropic" in actual_model or "claude" in actual_model:
                fallback_provider = "anthropic"
            else:
                fallback_provider = actual_model
            log.warning(
                "router_fallback_used",
                requested_model="gpt-4o-mini",
                actual_model=actual_model,
                fallback_provider=fallback_provider,
            )

        self._stream_partial = ParsedResponse(
            estimation="",
            response_id=last_id,
            input_tokens=usage_data.prompt_tokens if usage_data else 0,
            output_tokens=usage_data.completion_tokens if usage_data else 0,
            reasoning_tokens=None,
            finish_reason="stop",
            truncated=False,
            fallback_provider=fallback_provider,
        )
