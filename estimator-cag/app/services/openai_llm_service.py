from typing import Any, Optional

import tiktoken
from openai import AsyncOpenAI

from app.config import settings
from app.services.base_llm_service import BaseLLMService

# --------------------------------------------------------------------------- #
# Model registry — pricing in USD per 1 M tokens
# --------------------------------------------------------------------------- #
MODELS: dict[str, dict[str, Any]] = {
    "gpt-3.5-turbo": {
        "input_price": 0.50,
        "output_price": 1.50,
        "encoding": "cl100k_base",
        "context_window": 16_385,
        "reasoning": False,
    },
    "gpt-4-turbo": {
        "input_price": 10.0,
        "output_price": 30.0,
        "encoding": "cl100k_base",
        "context_window": 128_000,
        "reasoning": False,
    },
    "gpt-4o-mini": {
        "input_price": 0.15,
        "output_price": 0.60,
        "encoding": "o200k_base",
        "context_window": 128_000,
        "reasoning": False,
    },
    "gpt-5.4-mini": {
        "input_price": 0.75,
        "output_price": 4.50,
        "encoding": "o200k_base",
        "context_window": 128_000,
        "reasoning": False,
    },
    "gpt-5.4": {
        "input_price": 2.50,
        "output_price": 15.00,
        "encoding": "o200k_base",
        "context_window": 128_000,
        "reasoning": False,
    },
    "o3-mini": {
        "input_price": 1.10,
        "output_price": 4.40,
        "encoding": "o200k_base",
        "context_window": 200_000,
        "reasoning": True,
    },
    "o3": {
        "input_price": 10.0,
        "output_price": 40.0,
        "encoding": "o200k_base",
        "context_window": 200_000,
        "reasoning": True,
    },
    "o4-mini": {
        "input_price": 1.10,
        "output_price": 4.40,
        "encoding": "o200k_base",
        "context_window": 200_000,
        "reasoning": True,
    },
    "o4-mini-2025-04-16": {
        "input_price": 1.10,
        "output_price": 4.40,
        "encoding": "o200k_base",
        "context_window": 200_000,
        "reasoning": True,
    },
}

DEFAULT_MODEL: str = (
    settings.llm_model
    if settings.llm_provider.lower() == "openai" and settings.llm_model in MODELS
    else "gpt-4o-mini"
)

# Tokens added by the API per message (role overhead) and response priming
_MSG_OVERHEAD: int = 4
_PRIMING_TOKENS: int = 2

# --------------------------------------------------------------------------- #
# Lazy client factory
# --------------------------------------------------------------------------- #
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# --------------------------------------------------------------------------- #
# OpenAI implementation
# --------------------------------------------------------------------------- #
class OpenAILLMService(BaseLLMService):
    """LLM service implementation backed by the OpenAI Responses API."""

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
        encoding_name = (MODELS.get(model) or {}).get("encoding")
        if encoding_name:
            encoding = tiktoken.get_encoding(encoding_name)
        else:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")

        tokens = 0
        for text in (system_prompt, user_message):
            tokens += len(encoding.encode(text)) + _MSG_OVERHEAD
        tokens += _PRIMING_TOKENS
        return tokens

    def _build_api_params(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        transcription: str,
        model_info: dict[str, Any],
        temperature: Optional[float],
        top_p: Optional[float],
        reasoning_effort: str,
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": resolved_model,
            "instructions": system_prompt,   # [system] — role + CAG examples
            "input": transcription,          # [user]   — meeting transcription
            "max_output_tokens": max_output_tokens,
            "store": continue_conversation,
        }

        if model_info["reasoning"]:
            params["reasoning"] = {"effort": reasoning_effort}
        else:
            if temperature is not None:
                params["temperature"] = temperature
            elif top_p is not None:
                params["top_p"] = top_p

        if continue_conversation and self._last_response_id:
            params["previous_response_id"] = self._last_response_id

        return params

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        return await _get_client().responses.create(**api_params)

    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> dict[str, Any]:
        if response.status != "completed":
            return {
                "error": True,
                "type": response.status,
                "message": f"Response ended with status '{response.status}'.",
            }

        usage = response.usage
        reasoning_tokens: Optional[int] = None
        if is_reasoning and usage.output_tokens_details:
            reasoning_tokens = usage.output_tokens_details.reasoning_tokens

        return {
            "content": response.output_text,
            "response_id": response.id,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": reasoning_tokens,
        }


# --------------------------------------------------------------------------- #
# Module-level singleton + backward-compatible public API
# --------------------------------------------------------------------------- #
_openai_service = OpenAILLMService()


def estimate_call_tokens(
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> int:
    """Return the estimated number of input tokens for a system+user call.

    Uses tiktoken to count tokens and adds per-message overhead and priming
    tokens following OpenAI's documented formula.
    """
    return _openai_service._count_tokens(system_prompt, user_message, model)


async def estimate(
    transcription: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    reasoning_effort: str = "medium",
    max_output_tokens: int = 2_048,
    continue_conversation: bool = False,
) -> dict[str, Any]:
    """Generate a software effort estimate from a meeting transcription.

    Delegates to :class:`OpenAILLMService`, which inherits the shared
    PRE-CALL / CALL / POST-CALL pipeline from :class:`BaseLLMService`.
    """
    return await _openai_service.estimate(
        transcription,
        model=model,
        temperature=temperature,
        top_p=top_p,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        continue_conversation=continue_conversation,
    )
