from typing import Any, Optional

from anthropic import (
    APIConnectionError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.config import settings
from app.services.base_llm_service import BaseLLMService

# --------------------------------------------------------------------------- #
# Model registry — pricing in USD per 1 M tokens
# --------------------------------------------------------------------------- #
MODELS: dict[str, dict[str, Any]] = {
    "claude-haiku-4-5-20251001": {
        "input_price": 1.00,
        "output_price": 5.00,
        "context_window": 200_000,
        "reasoning": False,
    },
    "claude-sonnet-4-6": {
        "input_price": 3.00,
        "output_price": 15.00,
        "context_window": 200_000,
        "reasoning": False,
    },
    "claude-opus-4-7": {
        "input_price": 15.00,
        "output_price": 75.00,
        "context_window": 200_000,
        "reasoning": False,
    },
}

DEFAULT_MODEL: str = "claude-sonnet-4-6"

# Approximate chars-per-token ratio used for pre-call token estimation.
# Anthropic's tokenizer is not available offline; 3.5 chars/token is a
# conservative estimate that avoids underestimating context usage.
_CHARS_PER_TOKEN: float = 3.5

# --------------------------------------------------------------------------- #
# Lazy client factory
# --------------------------------------------------------------------------- #
_client: Optional[AsyncAnthropic] = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


# --------------------------------------------------------------------------- #
# Anthropic implementation
# --------------------------------------------------------------------------- #
class AnthropicLLMService(BaseLLMService):
    """LLM service implementation backed by the Anthropic Messages API."""

    def _get_model_info(
        self, model: Optional[str]
    ) -> tuple[str, dict[str, Any]]:
        resolved = model or DEFAULT_MODEL
        info = MODELS.get(resolved)
        if info is None:
            raise ValueError(
                f"Unknown model '{resolved}'. Add it to the MODELS registry."
            )
        return resolved, info

    def _count_tokens(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
    ) -> int:
        """Estimate token count using a character-based heuristic.

        Anthropic does not provide an offline tokenizer. The approximation
        (total_chars / 3.5) is conservative enough to avoid underestimating
        context usage in the pre-call overflow check.
        """
        total_chars = len(system_prompt) + len(user_message)
        return int(total_chars / _CHARS_PER_TOKEN)

    def _build_api_params(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        transcription: str,
        model_info: dict[str, Any],
        temperature: Optional[float],
        top_p: Optional[float],
        top_k: Optional[int],
        reasoning_effort: str,
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": resolved_model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": transcription}],
            "max_tokens": max_output_tokens,
        }

        # Anthropic API: temperature is mutually exclusive with top_p AND top_k
        if top_p is not None:
            params["top_p"] = top_p
        elif top_k is not None:
            params["top_k"] = top_k
        else:
            if temperature is not None:
                params["temperature"] = temperature

        return params

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        try:
            return await _get_client().messages.create(**api_params)
        except AuthenticationError:
            return {
                "error": True,
                "type": "authentication_error",
                "message": "Invalid or missing Anthropic API key.",
                "status_code": 401,
            }
        except RateLimitError:
            return {
                "error": True,
                "type": "rate_limit_error",
                "message": "Rate limit reached or insufficient credit.",
                "status_code": 429,
            }
        except BadRequestError as exc:
            return {
                "error": True,
                "type": "bad_request_error",
                "message": f"Invalid request: {exc.message}",
                "status_code": 400,
            }
        except (APIConnectionError, InternalServerError) as exc:
            return {
                "error": True,
                "type": "connection_error",
                "message": f"Connection or server error: {exc}",
                "status_code": 503,
            }

    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> dict[str, Any]:
        # max_tokens means the response was truncated but content is usable —
        # return it with a warning flag instead of discarding it as an error.
        if response.stop_reason not in ("end_turn", "stop_sequence", "max_tokens"):
            return {
                "error": True,
                "type": response.stop_reason or "unknown",
                "message": (
                    f"Response ended with stop_reason '{response.stop_reason}'."
                ),
            }

        return {
            "content": response.content[0].text,
            "response_id": response.id,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "reasoning_tokens": None,  # Anthropic does not expose reasoning tokens
            "truncated": response.stop_reason == "max_tokens",
        }
