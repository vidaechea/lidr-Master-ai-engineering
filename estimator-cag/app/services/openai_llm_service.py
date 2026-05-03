from collections.abc import AsyncIterator
from typing import Any, Optional

import tiktoken
from openai import (
    APIConnectionError,
    AsyncOpenAI,
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

    _ERROR_MAPPING = {
        **BaseLLMService._build_provider_error_mapping(
            provider_label="OpenAI",
            auth_error_type=AuthenticationError,
            rate_limit_type=RateLimitError,
            bad_request_type=BadRequestError,
            connection_type=APIConnectionError,
            internal_error_type=InternalServerError,
        )
    }

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
            params["text"] = {"format": {"type": "text"}}
        else:
            if temperature is not None:
                params["temperature"] = temperature
            elif top_p is not None:
                params["top_p"] = top_p

        if continue_conversation and self._last_response_id:
            params["previous_response_id"] = self._last_response_id

        return params

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        try:
            return await _get_client().responses.create(**api_params)
        except (
            AuthenticationError,
            RateLimitError,
            BadRequestError,
            APIConnectionError,
            InternalServerError,
        ) as exc:
            self._raise_service_error(exc, self._ERROR_MAPPING)

    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> dict[str, Any]:
        if response.status != "completed":
            raise LLMServiceError(
                response.status,
                f"Response ended with status '{response.status}'.",
            )

        usage = response.usage
        reasoning_tokens: Optional[int] = None
        if is_reasoning and usage.output_tokens_details:
            reasoning_tokens = usage.output_tokens_details.reasoning_tokens

        return {
            "estimation": response.output_text,
            "response_id": response.id,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "finish_reason": "stop",
        }

    async def _call_provider_stream(
        self,
        api_params: dict[str, Any],
        *,
        is_reasoning: bool,
    ) -> AsyncIterator[str]:
        # Use create(stream=True) with raw SSE events instead of the higher-level
        # responses.stream() helper, which has a bug in SDK v2.32.0 when the
        # response object inside events arrives as a plain dict.
        final_response = None
        try:
            raw_stream = await _get_client().responses.create(**api_params, stream=True)
            async for event in raw_stream:
                event_type = getattr(event, "type", None)
                if event_type == "response.output_text.delta":
                    yield event.delta
                elif event_type == "response.completed":
                    final_response = event.response
        except (
            AuthenticationError,
            RateLimitError,
            BadRequestError,
            APIConnectionError,
            InternalServerError,
        ) as exc:
            self._raise_service_error(exc, self._ERROR_MAPPING)

        if final_response is None:
            raise LLMServiceError(
                "stream_error",
                "Stream ended without a response.completed event.",
                500,
            )

        usage = final_response.usage
        reasoning_tokens: int | None = None
        if is_reasoning and usage.output_tokens_details:
            reasoning_tokens = usage.output_tokens_details.reasoning_tokens

        self._stream_partial = {
            "response_id": final_response.id,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "finish_reason": "stop",
            "truncated": False,
        }
