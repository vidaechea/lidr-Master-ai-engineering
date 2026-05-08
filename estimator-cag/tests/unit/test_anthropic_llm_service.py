"""Unit tests for AnthropicLLMService — no facade, no OpenAI dependency."""
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

import app.services.anthropic_llm_service as anthropic_svc
from app.config import settings
from app.services.anthropic_llm_service import (
    DEFAULT_MODEL,
    MODELS,
    _CACHE_READ_PRICE_MULTIPLIER,
    _CACHE_WRITE_PRICE_MULTIPLIER,
    _CHARS_PER_TOKEN,
    _THINKING_BUDGET,
    AnthropicLLMService,
)
from app.services.base_llm_service import LLMServiceError

FAKE_OUTPUT = "## Estimate: E-commerce Platform\n\n1. Backend: 60 hours\n\n**Total: 60 hours**"
FAKE_RESPONSE_ID = "msg_abc123"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@dataclass
class _StreamUsage:
    input_tokens: int
    output_tokens: int
    thinking_tokens: int | None = None
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _StreamFinal:
    id: str
    usage: _StreamUsage
    stop_reason: str


class _DummyStream:
    def __init__(self, deltas: list[str], final: _StreamFinal) -> None:
        self._deltas = deltas
        self._final = final

    async def __aenter__(self) -> "_DummyStream":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get_final_message(self) -> _StreamFinal:
        return self._final

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            for delta in self._deltas:
                yield delta

        return _gen()

def _make_response_mock(
    output_text: str = FAKE_OUTPUT,
    stop_reason: str = "end_turn",
    input_tokens: int = 500,
    output_tokens: int = 200,
    response_id: str = FAKE_RESPONSE_ID,
    thinking_text: str | None = None,
    thinking_tokens: int | None = None,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> MagicMock:
    """Build a minimal mock that mimics an Anthropic Messages API response object.

    When *thinking_text* is provided, the content list starts with a thinking
    block followed by the text block, mirroring Extended Thinking responses.
    """
    usage = MagicMock(
        spec=[
            "input_tokens",
            "output_tokens",
            "thinking_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ]
    )
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.thinking_tokens = thinking_tokens
    usage.cache_creation_input_tokens = cache_creation_input_tokens
    usage.cache_read_input_tokens = cache_read_input_tokens

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = output_text

    if thinking_text is not None:
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = thinking_text
        content = [thinking_block, text_block]
    else:
        content = [text_block]

    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content
    response.usage = usage
    response.id = response_id
    return response


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def reset_client():
    """Reset the lazy Anthropic client singleton before every test."""
    anthropic_svc._client = None
    yield
    anthropic_svc._client = None


@pytest.fixture(autouse=True)
def clear_env_model():
    """Prevent LLM_MODEL from the .env file from polluting unit tests.

    Unit tests pass model=None to let the service fall back to DEFAULT_MODEL.
    Without this fixture, a locally set LLM_MODEL (e.g. claude-opus-4-7) would
    override DEFAULT_MODEL and break assertions that expect the default.
    """
    import app.services.anthropic_llm_service as svc_mod
    original = svc_mod.settings.llm_model
    svc_mod.settings.llm_model = ""
    yield
    svc_mod.settings.llm_model = original


@pytest.fixture
def service() -> AnthropicLLMService:
    """Fresh AnthropicLLMService instance per test — state is always clean."""
    return AnthropicLLMService()


# --------------------------------------------------------------------------- #
# _count_tokens — character-based heuristic
# --------------------------------------------------------------------------- #

class TestCountTokens:
    def test_returns_positive_integer(self, service):
        tokens = service._count_tokens("You are an expert.", "Build a CRUD app.", DEFAULT_MODEL)
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_longer_inputs_produce_more_tokens(self, service):
        short = service._count_tokens("system", "short", DEFAULT_MODEL)
        long = service._count_tokens("system", "short " * 200, DEFAULT_MODEL)
        assert long > short

    def test_estimate_based_on_char_ratio(self, service):
        system = "a" * 350
        user = "b" * 350
        # total_chars = 700, ceil(700 / 3.5) = 200
        expected = max(1, math.ceil(700 / _CHARS_PER_TOKEN))
        assert service._count_tokens(system, user, DEFAULT_MODEL) == expected

    def test_model_argument_ignored_for_heuristic(self, service):
        """Token count must be the same regardless of model — heuristic is model-agnostic."""
        t1 = service._count_tokens("text", "message", "claude-haiku-4-5-20251001")
        t2 = service._count_tokens("text", "message", "claude-opus-4-7")
        assert t1 == t2


# --------------------------------------------------------------------------- #
# estimate — success path
# --------------------------------------------------------------------------- #

class TestEstimateSuccess:
    @pytest.fixture
    def mock_response(self):
        return _make_response_mock()

    async def test_returns_dict(self, service, mock_response):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert isinstance(result, dict)

    async def test_content_equals_first_content_block(self, service, mock_response):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["estimation"] == FAKE_OUTPUT

    async def test_model_key_matches_resolved_model(self, service, mock_response):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["model"] == DEFAULT_MODEL

    async def test_response_id_matches(self, service, mock_response):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["response_id"] == FAKE_RESPONSE_ID

    async def test_token_counts_come_from_usage(self, service, mock_response):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["input_tokens"] == mock_response.usage.input_tokens
        assert result["output_tokens"] == mock_response.usage.output_tokens

    async def test_reasoning_tokens_none_for_non_reasoning_model(self, service, mock_response):
        """Non-reasoning models never expose reasoning tokens."""
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["reasoning_tokens"] is None

    async def test_turn_cost_is_positive_float(self, service, mock_response):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert isinstance(result["turn_cost_usd"], float)
        assert result["turn_cost_usd"] > 0

    async def test_turn_cost_calculation(self, service, mock_response):
        info = MODELS[DEFAULT_MODEL]
        expected = round(
            (
                mock_response.usage.input_tokens * info.input_price
                + mock_response.usage.output_tokens * info.output_price
                # cache tokens are 0 in mock_response — no adjustment expected
            )
            / 1_000_000,
            8,
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["turn_cost_usd"] == expected

    async def test_stop_sequence_also_succeeds(self, service):
        """stop_sequence is an accepted success stop_reason alongside end_turn."""
        mock_response = _make_response_mock(stop_reason="stop_sequence")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert "error" not in result


# --------------------------------------------------------------------------- #
# _get_client — lazy singleton
# --------------------------------------------------------------------------- #


class TestGetClient:
    def test_client_is_cached(self, monkeypatch) -> None:
        class DummyClient:
            def __init__(self, api_key: str) -> None:
                self.api_key = api_key

        monkeypatch.setattr(anthropic_svc, "AsyncAnthropic", DummyClient)
        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        anthropic_svc._client = None

        first = anthropic_svc._get_client()
        second = anthropic_svc._get_client()

        assert first is second
        assert first.api_key == "test-key"


# --------------------------------------------------------------------------- #
# estimate — API error propagation
# --------------------------------------------------------------------------- #

class TestEstimateApiErrors:
    async def test_max_tokens_returns_content_with_truncated_flag(self, service):
        """max_tokens is a warning: partial content is returned, not discarded."""
        mock_response = _make_response_mock(stop_reason="max_tokens")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build something")
        assert "error" not in result
        assert result.get("truncated") is True
        assert result.get("estimation") == FAKE_OUTPUT

    async def test_non_truncated_response_has_truncated_false(self, service):
        mock_response = _make_response_mock(stop_reason="end_turn")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build something")
        assert result.get("truncated") is False

    async def test_unknown_stop_reason_raises_llm_service_error(self, service):
        mock_response = _make_response_mock(stop_reason="tool_use")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("Build something")
        assert exc_info.value.error_type == "tool_use"
        assert exc_info.value.message


# --------------------------------------------------------------------------- #
# _call_provider_stream — streaming
# --------------------------------------------------------------------------- #


class TestCallProviderStream:
    @pytest.mark.asyncio
    async def test_stream_emits_deltas_and_sets_partial(self, service: AnthropicLLMService) -> None:
        final = _StreamFinal(
            id="msg_stream",
            usage=_StreamUsage(input_tokens=9, output_tokens=4),
            stop_reason="end_turn",
        )
        dummy_stream = _DummyStream(["Hello ", "world"], final)
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.stream = MagicMock(return_value=dummy_stream)
            deltas: list[str] = []
            async for delta in service._call_provider_stream({"model": DEFAULT_MODEL}, is_reasoning=False):
                deltas.append(delta)

        assert "".join(deltas) == "Hello world"
        assert service._stream_partial["response_id"] == "msg_stream"
        assert service._stream_partial["finish_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_stream_reasoning_and_cache_tokens(self, service: AnthropicLLMService) -> None:
        usage = _StreamUsage(
            input_tokens=11,
            output_tokens=7,
            thinking_tokens=123,
            cache_creation_input_tokens=5,
            cache_read_input_tokens=3,
        )
        final = _StreamFinal(id="msg_stream", usage=usage, stop_reason="max_tokens")
        dummy_stream = _DummyStream(["OK"], final)
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.stream = MagicMock(return_value=dummy_stream)
            async for _ in service._call_provider_stream({"model": DEFAULT_MODEL}, is_reasoning=True):
                pass

        assert service._stream_partial["reasoning_tokens"] == 123
        assert service._stream_partial["truncated"] is True
        assert service._stream_partial["cache_creation_tokens"] == 5
        assert service._stream_partial["cache_read_tokens"] == 3


# --------------------------------------------------------------------------- #
# estimate — provider exception handling
# --------------------------------------------------------------------------- #

class TestEstimateProviderExceptions:
    async def test_authentication_error_raises_401(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=AuthenticationError(
                    message="Invalid key", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_type == "authentication_error"

    async def test_rate_limit_error_raises_429(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=RateLimitError(
                    message="Rate limit", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 429
        assert exc_info.value.error_type == "rate_limit_error"

    async def test_bad_request_error_raises_400(self, service):
        exc = BadRequestError(message="Bad input", response=MagicMock(), body={})
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(side_effect=exc)
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 400
        assert exc_info.value.error_type == "bad_request_error"
        assert "Bad input" in exc_info.value.message

    async def test_connection_error_raises_503(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=APIConnectionError(request=MagicMock())
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_type == "connection_error"

    async def test_internal_server_error_raises_503(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=InternalServerError(
                    message="Server error", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_type == "connection_error"


# --------------------------------------------------------------------------- #
# estimate — parameter routing (temperature / top_p / top_k mutex)
# --------------------------------------------------------------------------- #

class TestEstimateParamRouting:
    async def test_temperature_sent_when_provided(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", temperature=0.7)
        assert create_mock.call_args.kwargs.get("temperature") == 0.7

    async def test_top_p_sent_when_provided(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", top_p=0.9)
        assert create_mock.call_args.kwargs.get("top_p") == 0.9

    async def test_top_k_sent_when_provided(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", top_k=5)
        assert create_mock.call_args.kwargs.get("top_k") == 5

    async def test_top_k_excludes_temperature(self, service):
        """When top_k is set, temperature must NOT be forwarded to the API."""
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", top_k=5, temperature=0.7)
        params = create_mock.call_args.kwargs
        assert params.get("top_k") == 5
        assert "temperature" not in params

    async def test_temperature_not_sent_when_omitted(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test")
        assert "temperature" not in create_mock.call_args.kwargs


# --------------------------------------------------------------------------- #
# estimate — verbosity (ignored by Anthropic)
# --------------------------------------------------------------------------- #

class TestEstimateIgnoredParams:
    """verbosity is part of the base contract but the Anthropic Messages API
    has no equivalent parameter.  It must be silently dropped — never forwarded
    to messages.create — and must never raise a TypeError."""

    async def test_verbosity_low_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", verbosity="low")
        assert "estimation" in result

    async def test_verbosity_medium_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", verbosity="medium")
        assert "estimation" in result

    async def test_verbosity_high_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", verbosity="high")
        assert "estimation" in result

    async def test_verbosity_not_forwarded_to_api(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", verbosity="high")
        assert "verbosity" not in create_mock.call_args.kwargs

    def test_build_api_params_accepts_verbosity_keyword(self, service):
        """Direct call to _build_api_params with verbosity must not raise TypeError."""
        resolved_model = DEFAULT_MODEL
        info = MODELS[resolved_model]
        params = service._build_api_params(
            resolved_model=resolved_model,
            system_prompt="system",
            transcription="user message",
            model_info=info,
            temperature=None,
            top_p=None,
            top_k=None,
            reasoning_effort="medium",
            verbosity="high",
            max_output_tokens=1024,
            continue_conversation=False,
        )
        assert "verbosity" not in params


# --------------------------------------------------------------------------- #
# estimate — PRE-CALL validation (inherited from BaseLLMService)
# --------------------------------------------------------------------------- #

class TestEstimateValidation:
    async def test_raises_when_both_temperature_and_top_p_set(self, service):
        with pytest.raises(ValueError, match="mutually exclusive"):
            await service.estimate("test", temperature=0.5, top_p=0.9)

    async def test_raises_when_model_not_in_registry(self, service):
        with pytest.raises(ValueError, match="Unknown model"):
            await service.estimate("test", model="nonexistent-model")

    async def test_raises_llm_service_error_on_context_overflow(self, service):
        with patch.object(service, "_count_tokens", return_value=999_999_999):
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 413
        assert "overflow" in exc_info.value.error_type


# --------------------------------------------------------------------------- #
# Multi-turn stateless history
# --------------------------------------------------------------------------- #

class TestMultiTurn:
    async def test_single_turn_sends_only_current_message(self, service):
        """continue_conversation=False → messages contains only the new user message."""
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("First call", continue_conversation=False)
        messages = create_mock.call_args.kwargs["messages"]
        assert messages == [{"role": "user", "content": "First call"}]

    async def test_first_continue_true_sends_single_message(self, service):
        """First call with continue_conversation=True — history empty, single message sent."""
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("Turn one", continue_conversation=True)
        messages = create_mock.call_args.kwargs["messages"]
        assert messages == [{"role": "user", "content": "Turn one"}]

    async def test_second_turn_includes_full_history(self, service):
        """Second call with continue_conversation=True includes [user, assistant, user]."""
        resp1 = _make_response_mock(output_text="Answer one", response_id="id1")
        resp2 = _make_response_mock(output_text="Answer two", response_id="id2")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(side_effect=[resp1, resp2])
            mock_client.return_value.messages.create = create_mock
            await service.estimate("Turn one", continue_conversation=True)
            await service.estimate("Turn two", continue_conversation=True)
        messages = create_mock.call_args.kwargs["messages"]
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "Turn one"}
        assert messages[1] == {"role": "assistant", "content": "Answer one"}
        assert messages[2] == {"role": "user", "content": "Turn two"}

    async def test_history_strictly_alternates_user_assistant(self, service):
        """After N turns, history must strictly alternate user → assistant."""
        responses = [
            _make_response_mock(output_text=f"Answer {i}", response_id=f"id{i}")
            for i in range(3)
        ]
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(side_effect=responses)
            mock_client.return_value.messages.create = create_mock
            for i in range(3):
                await service.estimate(f"Turn {i}", continue_conversation=True)
        for idx, msg in enumerate(service._conversation_history):
            expected_role = "user" if idx % 2 == 0 else "assistant"
            assert msg["role"] == expected_role, (
                f"Expected role '{expected_role}' at index {idx}, got '{msg['role']}'"
            )

    async def test_reset_clears_conversation_history(self, service):
        """reset() must wipe the history so the next turn starts from scratch."""
        resp1 = _make_response_mock(output_text="Answer one")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=resp1)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("Turn one", continue_conversation=True)
        assert len(service._conversation_history) == 2
        service.reset()
        assert service._conversation_history == []
        resp2 = _make_response_mock(output_text="Fresh start")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=resp2)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("After reset", continue_conversation=True)
        messages = create_mock.call_args.kwargs["messages"]
        assert messages == [{"role": "user", "content": "After reset"}]

    async def test_history_not_updated_on_api_error(self, service):
        """If the API call fails, conversation history must remain unchanged."""
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=RateLimitError(
                    message="Rate limit", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError):
                await service.estimate("Turn one", continue_conversation=True)
        assert service._conversation_history == []

    async def test_continue_false_does_not_append_to_history(self, service):
        """continue_conversation=False must not update conversation history."""
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("Single shot", continue_conversation=False)
        assert service._conversation_history == []

    async def test_continue_false_ignores_existing_history(self, service):
        """Even if history exists, continue_conversation=False sends only the new message."""
        resp1 = _make_response_mock(output_text="Answer one")
        resp2 = _make_response_mock(output_text="Answer two")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(side_effect=[resp1, resp2])
            mock_client.return_value.messages.create = create_mock
            await service.estimate("Turn one", continue_conversation=True)
            await service.estimate("Single shot", continue_conversation=False)
        messages = create_mock.call_args.kwargs["messages"]
        assert messages == [{"role": "user", "content": "Single shot"}]

    async def test_token_estimate_includes_history_chars(self, service):
        """_count_tokens must account for conversation history in the estimate."""
        service._conversation_history = [
            {"role": "user", "content": "a" * 700},
            {"role": "assistant", "content": "b" * 700},
        ]
        history_chars = 1400
        sys_chars = 10
        user_chars = 10
        expected = max(1, math.ceil((sys_chars + history_chars + user_chars) / _CHARS_PER_TOKEN))
        result = service._count_tokens("a" * sys_chars, "b" * user_chars, DEFAULT_MODEL)
        assert result == expected

    async def test_history_grows_with_each_turn(self, service):
        """Each successful turn appends exactly 2 items (user + assistant) to history."""
        responses = [
            _make_response_mock(output_text=f"A{i}", response_id=f"id{i}")
            for i in range(3)
        ]
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(side_effect=responses)
            mock_client.return_value.messages.create = create_mock
            for i in range(3):
                await service.estimate(f"Q{i}", continue_conversation=True)
                assert len(service._conversation_history) == (i + 1) * 2


# --------------------------------------------------------------------------- #
# Extended Thinking (claude-opus-4-7 and future reasoning models)
# --------------------------------------------------------------------------- #

class TestExtendedThinking:
    REASONING_MODEL = "claude-opus-4-7"

    def test_reasoning_model_is_flagged_in_registry(self):
        assert MODELS[self.REASONING_MODEL].reasoning is True

    def test_non_reasoning_models_not_flagged(self):
        for name, info in MODELS.items():
            if name != self.REASONING_MODEL:
                assert info.reasoning is False, f"{name} should have reasoning=False"

    async def test_thinking_param_sent_for_reasoning_model(self, service):
        """_build_api_params must include thinking block for reasoning models."""
        mock_response = _make_response_mock(thinking_text="I reason...")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", model=self.REASONING_MODEL)
        params = create_mock.call_args.kwargs
        assert "thinking" in params
        # claude-opus-4-7 only supports adaptive API
        assert params["thinking"]["type"] == "adaptive"
        assert "output_config" in params

    async def test_thinking_always_uses_high_effort(self, service):
        """Reasoning models always force effort=high regardless of reasoning_effort arg."""
        mock_response = _make_response_mock(thinking_text="I reason...")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", model=self.REASONING_MODEL, reasoning_effort="low")
        assert create_mock.call_args.kwargs["output_config"]["effort"] == "high"

    async def test_max_tokens_forced_to_8000_for_reasoning_model(self, service):
        """Reasoning models always use max_tokens=8000 regardless of caller value."""
        mock_response = _make_response_mock(thinking_text="I reason...")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", model=self.REASONING_MODEL, max_output_tokens=1024)
        assert create_mock.call_args.kwargs["max_tokens"] == 8_000

    async def test_temperature_not_sent_for_reasoning_model(self, service):
        """Extended Thinking is incompatible with custom temperature."""
        mock_response = _make_response_mock(thinking_text="I reason...")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", model=self.REASONING_MODEL, temperature=0.7)
        params = create_mock.call_args.kwargs
        assert "temperature" not in params
        assert "top_p" not in params
        assert "top_k" not in params

    async def test_text_extracted_from_mixed_content_blocks(self, service):
        """When content has [thinking, text] blocks, content key holds the text block."""
        mock_response = _make_response_mock(
            output_text="Final answer here.",
            thinking_text="Let me think step by step...",
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", model=self.REASONING_MODEL)
        assert result["estimation"] == "Final answer here."

    async def test_reasoning_tokens_read_from_usage_when_present(self, service):
        """reasoning_tokens is populated from usage.thinking_tokens when the API exposes it."""
        mock_response = _make_response_mock(
            thinking_text="Some reasoning...",
            thinking_tokens=312,
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", model=self.REASONING_MODEL)
        assert result["reasoning_tokens"] == 312

    async def test_reasoning_tokens_none_when_usage_field_absent_and_no_thinking_blocks(self, service):
        """reasoning_tokens is None when usage.thinking_tokens is absent and no thinking blocks."""
        mock_response = _make_response_mock()  # no thinking_text
        mock_response.usage.thinking_tokens = None
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", model=self.REASONING_MODEL)
        assert result["reasoning_tokens"] is None

    async def test_reasoning_tokens_estimated_from_thinking_blocks_when_usage_absent(self, service):
        """When usage.thinking_tokens is None, estimate from thinking block char length."""
        thinking_text = "a" * 350  # 350 chars / 3.5 = 100 tokens
        mock_response = _make_response_mock(thinking_text=thinking_text)
        mock_response.usage.thinking_tokens = None
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", model=self.REASONING_MODEL)
        assert result["reasoning_tokens"] == max(1, math.ceil(350 / _CHARS_PER_TOKEN))

    async def test_non_reasoning_model_has_no_thinking_param(self, service):
        """Non-reasoning models must NOT receive the thinking parameter."""
        mock_response = _make_response_mock()
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.messages.create = create_mock
            await service.estimate("test", model="claude-sonnet-4-6")
        assert "thinking" not in create_mock.call_args.kwargs


# --------------------------------------------------------------------------- #
# Prompt Caching — cache_creation_input_tokens / cache_read_input_tokens
# --------------------------------------------------------------------------- #

class TestPromptCaching:
    async def test_cache_tokens_zero_when_absent_from_usage(self, service):
        """When the API returns no cache fields, both cache token counts must be 0."""
        mock_response = _make_response_mock()  # cache fields default to 0
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["cache_creation_tokens"] == 0
        assert result["cache_read_tokens"] == 0

    async def test_cache_creation_tokens_propagated_to_result(self, service):
        """cache_creation_input_tokens from usage must be exposed in the response dict."""
        mock_response = _make_response_mock(cache_creation_input_tokens=1_200)
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["cache_creation_tokens"] == 1_200

    async def test_cache_read_tokens_propagated_to_result(self, service):
        """cache_read_input_tokens from usage must be exposed in the response dict."""
        mock_response = _make_response_mock(cache_read_input_tokens=4_500)
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["cache_read_tokens"] == 4_500

    async def test_cache_write_cost_adds_premium(self, service):
        """Cache write tokens are billed at 1.25× input_price — turn cost must reflect that."""
        cache_write = 2_000
        mock_response = _make_response_mock(
            input_tokens=500,
            output_tokens=200,
            cache_creation_input_tokens=cache_write,
        )
        info = MODELS[DEFAULT_MODEL]
        expected = round(
            (
                500 * info.input_price
                + 200 * info.output_price
                + cache_write * info.input_price * _CACHE_WRITE_PRICE_MULTIPLIER
            )
            / 1_000_000,
            8,
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["turn_cost_usd"] == expected

    async def test_cache_read_cost_applies_discount(self, service):
        """Cache read tokens are billed at 0.10× input_price — turn cost must reflect that."""
        cache_read = 10_000
        mock_response = _make_response_mock(
            input_tokens=500,
            output_tokens=200,
            cache_read_input_tokens=cache_read,
        )
        info = MODELS[DEFAULT_MODEL]
        expected = round(
            (
                500 * info.input_price
                + 200 * info.output_price
                + cache_read * info.input_price * _CACHE_READ_PRICE_MULTIPLIER
            )
            / 1_000_000,
            8,
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["turn_cost_usd"] == expected

    async def test_cache_read_cheaper_than_standard_input(self, service):
        """Reading the same number of tokens from cache must cost less than standard input."""
        tokens = 5_000
        mock_no_cache = _make_response_mock(input_tokens=tokens, output_tokens=0)
        mock_cached = _make_response_mock(
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=tokens,
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_no_cache)
            result_no_cache = await service.estimate("test")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_cached)
            result_cached = await service.estimate("test")
        assert result_cached["turn_cost_usd"] < result_no_cache["turn_cost_usd"]

    async def test_no_cache_tokens_cost_equals_standard_formula(self, service):
        """When cache tokens are absent, cost must equal the standard input+output formula."""
        mock_response = _make_response_mock(input_tokens=800, output_tokens=300)
        info = MODELS[DEFAULT_MODEL]
        expected = round(
            (800 * info.input_price + 300 * info.output_price) / 1_000_000, 8
        )
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["turn_cost_usd"] == expected
