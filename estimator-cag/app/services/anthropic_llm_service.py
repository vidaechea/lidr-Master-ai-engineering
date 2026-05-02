import math
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
from app.services.base_llm_service import BaseLLMService, LLMServiceError

# --------------------------------------------------------------------------- #
# Model registry — pricing in USD per 1 M tokens
# --------------------------------------------------------------------------- #

DEFAULT_MODEL: str = "claude-sonnet-4-6"

# Prompt caching price multipliers (relative to input_price per 1 M tokens).
# Anthropic charges 1.25× for writing to cache and 0.10× for reading from cache.
# Reference: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
_CACHE_WRITE_PRICE_MULTIPLIER: float = 1.25
_CACHE_READ_PRICE_MULTIPLIER: float = 0.10

MODELS: dict[str, dict[str, Any]] = {
    "claude-haiku-4-5-20251001": {
        "input_price": 1.00,
        "output_price": 5.00,
        "context_window": 200_000,
        "reasoning": False,
        "cache_write_price_multiplier": _CACHE_WRITE_PRICE_MULTIPLIER,
        "cache_read_price_multiplier": _CACHE_READ_PRICE_MULTIPLIER,
    },
    "claude-sonnet-4-6": {
        "input_price": 3.00,
        "output_price": 15.00,
        "context_window": 200_000,
        "reasoning": False,
        "cache_write_price_multiplier": _CACHE_WRITE_PRICE_MULTIPLIER,
        "cache_read_price_multiplier": _CACHE_READ_PRICE_MULTIPLIER,
    },
    "claude-opus-4-7": {
        "input_price": 15.00,
        "output_price": 75.00,
        "context_window": 200_000,
        "reasoning": True,   # Supports Extended Thinking
        "thinking_api": "adaptive",  # Only supported mode; uses thinking.type=adaptive + output_config.effort
        "cache_write_price_multiplier": _CACHE_WRITE_PRICE_MULTIPLIER,
        "cache_read_price_multiplier": _CACHE_READ_PRICE_MULTIPLIER,
    },
}

# Approximate chars-per-token ratio used for pre-call token estimation.
# Anthropic's tokenizer is not available offline; 3.5 chars/token is a
# conservative estimate that avoids underestimating context usage.
_CHARS_PER_TOKEN: float = 3.5

# Extended Thinking budget_tokens per reasoning_effort level.
# Minimum allowed by Anthropic is 1 024 tokens.
_THINKING_BUDGET: dict[str, int] = {
    "low": 1_024,
    "medium": 5_000,
    "high": 10_000,
}

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

    def __init__(self) -> None:
        super().__init__()
        # Full conversation history for stateless multi-turn sessions.
        # Anthropic does not store history server-side; we send it on every call.
        self._conversation_history: list[dict[str, str]] = []

    def reset(self) -> None:
        """Reset session state and clear conversation history."""
        super().reset()
        self._conversation_history = []

    def _get_model_info(
        self, model: Optional[str]
    ) -> tuple[str, dict[str, Any]]:
        # Priority: caller arg > LLM_MODEL env var (if valid for Anthropic) > DEFAULT_MODEL
        env_model = settings.llm_model if settings.llm_model in MODELS else None
        resolved = model or env_model or DEFAULT_MODEL
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

        When a conversation is in progress, history characters are included so
        the overflow guard accounts for the full messages array sent to the API.
        """
        history_chars = sum(len(m["content"]) for m in self._conversation_history)
        total_chars = len(system_prompt) + history_chars + len(user_message)
        return max(1, math.ceil(total_chars / _CHARS_PER_TOKEN))

    def _build_api_params(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        transcription: str,
        model_info: dict[str, Any],
        temperature: Optional[float],
        top_p: Optional[float],
        top_k: Optional[int] = None,
        reasoning_effort: str,
        verbosity: str,  # not supported by Anthropic — ignored
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]:
        # Anthropic is stateless — the full history must be sent on every call.
        # For a fresh single-turn call, send only the current user message.
        if continue_conversation:
            messages: list[dict[str, str]] = list(self._conversation_history)
            messages.append({"role": "user", "content": transcription})
        else:
            messages = [{"role": "user", "content": transcription}]

        params: dict[str, Any] = {
            "model": resolved_model,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": max_output_tokens,
        }

        if model_info.get("reasoning"):
            # Reasoning models: force high effort and enough token budget.
            # These values are non-negotiable for Extended Thinking to activate.
            params["max_tokens"] = 8_000
            thinking_api = model_info.get("thinking_api", "enabled")
            if thinking_api == "adaptive":
                params["thinking"] = {"type": "adaptive"}
                params["output_config"] = {"effort": "high"}
            else:
                budget = _THINKING_BUDGET["high"]
                params["thinking"] = {"type": "enabled", "budget_tokens": budget}
        else:
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
            raise LLMServiceError(
                "authentication_error",
                "Invalid or missing Anthropic API key.",
                401,
            )
        except RateLimitError:
            raise LLMServiceError(
                "rate_limit_error",
                "Rate limit reached or insufficient credit.",
                429,
            )
        except BadRequestError as exc:
            raise LLMServiceError(
                "bad_request_error",
                f"Invalid request: {exc.message}",
                400,
            )
        except (APIConnectionError, InternalServerError) as exc:
            raise LLMServiceError(
                "connection_error",
                f"Connection or server error: {exc}",
                503,
            )

    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> dict[str, Any]:
        # max_tokens means the response was truncated but content is usable —
        # return it with a warning flag instead of discarding it as an error.
        if response.stop_reason not in ("end_turn", "stop_sequence", "max_tokens"):
            raise LLMServiceError(
                response.stop_reason or "unknown",
                f"Response ended with stop_reason '{response.stop_reason}'.",
            )

        # Extended Thinking responses contain a list of typed content blocks:
        #   [{"type": "thinking", ...}, {"type": "text", ...}]
        # We must iterate to find the text block instead of assuming index 0.
        # NOTE: claude-opus-4-7 with thinking.type=adaptive does NOT expose
        # thinking blocks in content nor thinking_tokens in usage — the
        # reasoning is internal only. Future models using the "enabled" API
        # will return thinking blocks; the fallback below handles that case.
        text_content: str = ""
        thinking_chars: int = 0
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_content = block.text
            elif block_type == "thinking":
                # The SDK may expose the thinking text via different attributes
                # depending on the API variant (enabled vs adaptive).
                # Try all known attribute names in order of preference.
                raw = (
                    getattr(block, "thinking", None)
                    or getattr(block, "text", None)
                    or ""
                )
                thinking_chars += len(raw)

        # Reasoning tokens: prefer SDK field (future-proof), fall back to
        # char-based estimate from thinking block content.
        reasoning_tokens: Optional[int] = None
        if is_reasoning:
            sdk_thinking = getattr(response.usage, "thinking_tokens", None)
            if sdk_thinking is not None:
                reasoning_tokens = sdk_thinking
            elif thinking_chars > 0:
                reasoning_tokens = max(1, math.ceil(thinking_chars / _CHARS_PER_TOKEN))

        return {
            "content": text_content,
            "response_id": response.id,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "truncated": response.stop_reason == "max_tokens",
            "cache_creation_tokens": getattr(response.usage, "cache_creation_input_tokens", None) or 0,
            "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", None) or 0,
        }

    def _on_turn_complete(
        self,
        transcription: str,
        assistant_content: str,
    ) -> None:
        """Append the completed user/assistant turn to the local history."""
        self._conversation_history.append({"role": "user", "content": transcription})
        self._conversation_history.append({"role": "assistant", "content": assistant_content})
