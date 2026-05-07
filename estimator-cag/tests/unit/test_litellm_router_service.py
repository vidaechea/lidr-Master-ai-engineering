"""Unit tests for LiteLLMRouterService — written before the implementation (TDD Red phase)."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.base_llm_service import BaseLLMService, LLMServiceError
from app.services.litellm_router_service import (
    LOGICAL_MODEL,
    _FALLBACK_MODEL,
    LiteLLMRouterService,
)


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #


class TestLiteLLMRouterServiceStructure:
    def test_is_subclass_of_base_llm_service(self):
        assert issubclass(LiteLLMRouterService, BaseLLMService)

    def test_router_attribute_is_litellm_router(self):
        from litellm import Router

        service = LiteLLMRouterService()
        assert isinstance(service._router, Router)

    def test_router_has_two_model_entries(self):
        service = LiteLLMRouterService()
        assert len(service._router.model_list) == 2

    def test_primary_entry_uses_logical_model_name(self):
        service = LiteLLMRouterService()
        names = [entry["model_name"] for entry in service._router.model_list]
        assert LOGICAL_MODEL in names

    def test_fallback_entry_uses_fallback_model_name(self):
        service = LiteLLMRouterService()
        names = [entry["model_name"] for entry in service._router.model_list]
        assert _FALLBACK_MODEL in names

    def test_primary_and_fallback_names_are_distinct(self):
        assert LOGICAL_MODEL != _FALLBACK_MODEL

    def test_logical_model_constant_is_string(self):
        assert isinstance(LOGICAL_MODEL, str)
        assert len(LOGICAL_MODEL) > 0

    def test_fallback_model_constant_is_string(self):
        assert isinstance(_FALLBACK_MODEL, str)
        assert len(_FALLBACK_MODEL) > 0


# --------------------------------------------------------------------------- #
# Failover policy
# --------------------------------------------------------------------------- #


class TestRouterFailoverPolicy:
    """Verify the Router is constructed with the ordered failover policy."""

    def test_fallbacks_list_is_configured(self):
        service = LiteLLMRouterService()
        assert service._router.fallbacks is not None
        assert len(service._router.fallbacks) > 0

    def test_fallbacks_maps_primary_to_fallback(self):
        service = LiteLLMRouterService()
        mapping = service._router.fallbacks[0]
        assert LOGICAL_MODEL in mapping
        assert _FALLBACK_MODEL in mapping[LOGICAL_MODEL]

    def test_num_retries_comes_from_settings(self):
        from app.config import settings

        service = LiteLLMRouterService()
        assert service._router.num_retries == settings.router_num_retries

    def test_timeout_comes_from_settings(self):
        from app.config import settings

        service = LiteLLMRouterService()
        assert service._router.timeout == settings.router_timeout

    def test_allowed_fails_comes_from_settings(self):
        from app.config import settings

        service = LiteLLMRouterService()
        assert service._router.allowed_fails == settings.router_allowed_fails

    def test_cooldown_time_comes_from_settings(self):
        from app.config import settings

        service = LiteLLMRouterService()
        assert service._router.cooldown_time == settings.router_cooldown_time

    def test_primary_model_is_openai(self):
        service = LiteLLMRouterService()
        primary = next(
            e for e in service._router.model_list if e["model_name"] == LOGICAL_MODEL
        )
        assert "gpt" in primary["litellm_params"]["model"]

    def test_fallback_model_is_anthropic(self):
        service = LiteLLMRouterService()
        fallback = next(
            e for e in service._router.model_list if e["model_name"] == _FALLBACK_MODEL
        )
        assert "anthropic" in fallback["litellm_params"]["model"]


# --------------------------------------------------------------------------- #
# _get_model_info
# --------------------------------------------------------------------------- #


class TestGetModelInfo:
    def test_returns_logical_model_name(self):
        service = LiteLLMRouterService()
        resolved, _ = service._get_model_info(None)
        assert resolved == LOGICAL_MODEL

    def test_model_info_has_required_keys(self):
        service = LiteLLMRouterService()
        _, info = service._get_model_info(None)
        for key in ("input_price", "output_price", "context_window", "reasoning"):
            assert key in info, f"Missing key: {key}"

    def test_reasoning_is_false(self):
        service = LiteLLMRouterService()
        _, info = service._get_model_info(None)
        assert info["reasoning"] is False

    def test_context_window_is_positive(self):
        service = LiteLLMRouterService()
        _, info = service._get_model_info(None)
        assert info["context_window"] > 0

    def test_always_returns_logical_model_regardless_of_input(self):
        """The router decides the actual model — the caller always uses LOGICAL_MODEL."""
        service = LiteLLMRouterService()
        resolved, _ = service._get_model_info("gpt-4o-mini")
        assert resolved == LOGICAL_MODEL

        resolved2, _ = service._get_model_info("claude-opus-4-7")
        assert resolved2 == LOGICAL_MODEL


# --------------------------------------------------------------------------- #
# _count_tokens
# --------------------------------------------------------------------------- #


class TestCountTokens:
    def test_returns_positive_integer(self):
        service = LiteLLMRouterService()
        tokens = service._count_tokens("You are an expert.", "Build a CRUD app.", LOGICAL_MODEL)
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_longer_input_produces_more_tokens(self):
        service = LiteLLMRouterService()
        short = service._count_tokens("system", "short text", LOGICAL_MODEL)
        long = service._count_tokens("system", "short text " * 200, LOGICAL_MODEL)
        assert long > short


# --------------------------------------------------------------------------- #
# _build_api_params
# --------------------------------------------------------------------------- #


def _default_params(service: LiteLLMRouterService, **overrides) -> dict[str, Any]:
    defaults = dict(
        resolved_model=LOGICAL_MODEL,
        system_prompt="You are an expert.",
        transcription="Build an e-commerce app.",
        model_info={"reasoning": False},
        temperature=None,
        top_p=None,
        top_k=None,
        reasoning_effort="medium",
        verbosity="low",
        max_output_tokens=2048,
        continue_conversation=False,
    )
    defaults.update(overrides)
    return service._build_api_params(**defaults)


class TestBuildApiParams:
    def test_model_is_logical_name(self):
        service = LiteLLMRouterService()
        params = _default_params(service)
        assert params["model"] == LOGICAL_MODEL

    def test_messages_contains_system_and_user(self):
        service = LiteLLMRouterService()
        params = _default_params(service)
        assert len(params["messages"]) == 2
        assert params["messages"][0]["role"] == "system"
        assert params["messages"][1]["role"] == "user"

    def test_system_message_content_matches(self):
        service = LiteLLMRouterService()
        params = _default_params(service, system_prompt="Custom system prompt")
        assert params["messages"][0]["content"] == "Custom system prompt"

    def test_user_message_content_matches(self):
        service = LiteLLMRouterService()
        params = _default_params(service, transcription="Meeting about payments.")
        assert params["messages"][1]["content"] == "Meeting about payments."

    def test_max_tokens_is_set(self):
        service = LiteLLMRouterService()
        params = _default_params(service, max_output_tokens=512)
        assert params["max_tokens"] == 512

    def test_temperature_included_when_provided(self):
        service = LiteLLMRouterService()
        params = _default_params(service, temperature=0.7)
        assert params["temperature"] == 0.7

    def test_top_p_included_when_temperature_is_none(self):
        service = LiteLLMRouterService()
        params = _default_params(service, temperature=None, top_p=0.9)
        assert params["top_p"] == 0.9

    def test_temperature_absent_when_none(self):
        service = LiteLLMRouterService()
        params = _default_params(service, temperature=None)
        assert "temperature" not in params

    def test_top_k_included_when_provided(self):
        service = LiteLLMRouterService()
        params = _default_params(service, top_k=40)
        assert params["top_k"] == 40

    def test_top_k_absent_when_none(self):
        service = LiteLLMRouterService()
        params = _default_params(service, top_k=None)
        assert "top_k" not in params


# --------------------------------------------------------------------------- #
# _call_provider
# --------------------------------------------------------------------------- #


class TestCallProvider:
    async def test_delegates_to_router_acompletion(self):
        service = LiteLLMRouterService()
        mock_response = MagicMock()
        service._router.acompletion = AsyncMock(return_value=mock_response)

        result = await service._call_provider({"model": LOGICAL_MODEL, "messages": []})

        service._router.acompletion.assert_called_once_with(
            model=LOGICAL_MODEL, messages=[]
        )
        assert result is mock_response

    async def test_raises_llm_service_error_on_auth_failure(self):
        import litellm

        service = LiteLLMRouterService()
        service._router.acompletion = AsyncMock(
            side_effect=litellm.AuthenticationError(
                message="Invalid API key", llm_provider="openai", model="gpt-4o-mini"
            )
        )
        with pytest.raises(LLMServiceError) as exc_info:
            await service._call_provider({"model": LOGICAL_MODEL, "messages": []})
        assert exc_info.value.status_code == 401

    async def test_raises_llm_service_error_on_rate_limit(self):
        import litellm

        service = LiteLLMRouterService()
        service._router.acompletion = AsyncMock(
            side_effect=litellm.RateLimitError(
                message="Rate limit exceeded", llm_provider="openai", model="gpt-4o-mini"
            )
        )
        with pytest.raises(LLMServiceError) as exc_info:
            await service._call_provider({"model": LOGICAL_MODEL, "messages": []})
        assert exc_info.value.status_code == 429

    async def test_raises_llm_service_error_on_connection_failure(self):
        import litellm

        service = LiteLLMRouterService()
        service._router.acompletion = AsyncMock(
            side_effect=litellm.APIConnectionError(
                message="Connection failed", llm_provider="openai", model="gpt-4o-mini"
            )
        )
        with pytest.raises(LLMServiceError) as exc_info:
            await service._call_provider({"model": LOGICAL_MODEL, "messages": []})
        assert exc_info.value.status_code == 503


# --------------------------------------------------------------------------- #
# _parse_provider_response
# --------------------------------------------------------------------------- #


def _make_litellm_response(
    content: str = "# Estimate",
    response_id: str = "chatcmpl-001",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    finish_reason: str = "stop",
) -> MagicMock:
    response = MagicMock()
    response.id = response_id
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


class TestParseProviderResponse:
    def test_extracts_text_content(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response(content="# Estimate\n1. Task: 10h")
        result = service._parse_provider_response(response, is_reasoning=False)
        assert result["estimation"] == "# Estimate\n1. Task: 10h"

    def test_extracts_input_token_count(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response(prompt_tokens=200)
        result = service._parse_provider_response(response, is_reasoning=False)
        assert result["input_tokens"] == 200

    def test_extracts_output_token_count(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response(completion_tokens=80)
        result = service._parse_provider_response(response, is_reasoning=False)
        assert result["output_tokens"] == 80

    def test_extracts_response_id(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response(response_id="chatcmpl-xyz")
        result = service._parse_provider_response(response, is_reasoning=False)
        assert result["response_id"] == "chatcmpl-xyz"

    def test_reasoning_tokens_is_always_none(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response()
        result = service._parse_provider_response(response, is_reasoning=False)
        assert result["reasoning_tokens"] is None

    def test_finish_reason_extracted(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response(finish_reason="length")
        result = service._parse_provider_response(response, is_reasoning=False)
        assert result["finish_reason"] == "length"

    def test_result_has_all_required_keys(self):
        service = LiteLLMRouterService()
        response = _make_litellm_response()
        result = service._parse_provider_response(response, is_reasoning=False)
        for key in ("estimation", "response_id", "input_tokens", "output_tokens", "reasoning_tokens", "finish_reason"):
            assert key in result, f"Missing key: {key}"


# --------------------------------------------------------------------------- #
# _call_provider_stream
# --------------------------------------------------------------------------- #


def _make_text_chunk(content: str, chunk_id: str = "s1") -> MagicMock:
    chunk = MagicMock()
    chunk.id = chunk_id
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = content
    chunk.usage = None
    return chunk


def _make_usage_chunk(
    prompt_tokens: int,
    completion_tokens: int,
    chunk_id: str = "s1",
) -> MagicMock:
    """Final chunk: empty choices, usage populated."""
    chunk = MagicMock()
    chunk.id = chunk_id
    chunk.choices = []
    chunk.usage = MagicMock()
    chunk.usage.prompt_tokens = prompt_tokens
    chunk.usage.completion_tokens = completion_tokens
    return chunk


class TestCallProviderStream:
    async def test_yields_text_deltas(self):
        service = LiteLLMRouterService()

        async def fake_stream():
            yield _make_text_chunk("Hello ")
            yield _make_text_chunk("world")
            yield _make_usage_chunk(10, 5)

        service._router.acompletion = AsyncMock(return_value=fake_stream())
        deltas = []
        async for delta in service._call_provider_stream(
            {"model": LOGICAL_MODEL, "messages": []}, is_reasoning=False
        ):
            deltas.append(delta)

        assert deltas == ["Hello ", "world"]

    async def test_does_not_yield_none_content(self):
        service = LiteLLMRouterService()

        async def fake_stream():
            yield _make_text_chunk("text")
            none_chunk = _make_text_chunk("")
            none_chunk.choices[0].delta.content = None
            yield none_chunk
            yield _make_usage_chunk(5, 3)

        service._router.acompletion = AsyncMock(return_value=fake_stream())
        deltas = []
        async for delta in service._call_provider_stream(
            {"model": LOGICAL_MODEL, "messages": []}, is_reasoning=False
        ):
            deltas.append(delta)

        assert deltas == ["text"]

    async def test_stream_partial_input_tokens_set_after_completion(self):
        service = LiteLLMRouterService()

        async def fake_stream():
            yield _make_text_chunk("result")
            yield _make_usage_chunk(prompt_tokens=15, completion_tokens=8)

        service._router.acompletion = AsyncMock(return_value=fake_stream())
        async for _ in service._call_provider_stream(
            {"model": LOGICAL_MODEL, "messages": []}, is_reasoning=False
        ):
            pass

        assert service._stream_partial["input_tokens"] == 15

    async def test_stream_partial_output_tokens_set_after_completion(self):
        service = LiteLLMRouterService()

        async def fake_stream():
            yield _make_text_chunk("result")
            yield _make_usage_chunk(prompt_tokens=15, completion_tokens=8)

        service._router.acompletion = AsyncMock(return_value=fake_stream())
        async for _ in service._call_provider_stream(
            {"model": LOGICAL_MODEL, "messages": []}, is_reasoning=False
        ):
            pass

        assert service._stream_partial["output_tokens"] == 8

    async def test_stream_partial_has_all_required_keys(self):
        service = LiteLLMRouterService()

        async def fake_stream():
            yield _make_text_chunk("ok")
            yield _make_usage_chunk(10, 5)

        service._router.acompletion = AsyncMock(return_value=fake_stream())
        async for _ in service._call_provider_stream(
            {"model": LOGICAL_MODEL, "messages": []}, is_reasoning=False
        ):
            pass

        for key in ("response_id", "input_tokens", "output_tokens", "reasoning_tokens", "finish_reason", "truncated"):
            assert key in service._stream_partial, f"Missing key: {key}"

    async def test_stream_includes_usage_in_request(self):
        """Verifies stream_options with include_usage is passed to router."""
        service = LiteLLMRouterService()

        async def fake_stream():
            yield _make_text_chunk("ok")
            yield _make_usage_chunk(5, 3)

        service._router.acompletion = AsyncMock(return_value=fake_stream())
        async for _ in service._call_provider_stream(
            {"model": LOGICAL_MODEL, "messages": []}, is_reasoning=False
        ):
            pass

        call_kwargs = service._router.acompletion.call_args.kwargs
        assert call_kwargs.get("stream") is True
        assert call_kwargs.get("stream_options") == {"include_usage": True}
