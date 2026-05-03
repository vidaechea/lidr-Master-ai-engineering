"""Unit tests for OpenAILLMService — no facade, no Anthropic dependency."""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import tiktoken
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

import app.services.openai_llm_service as openai_svc
from app.config import settings
from app.context.examples import EXAMPLE_HEADER_TEMPLATE
from app.services.base_llm_service import LLMServiceError
from app.services.openai_llm_service import (
    DEFAULT_MODEL,
    MODELS,
    _MSG_OVERHEAD,
    _PRIMING_TOKENS,
    OpenAILLMService,
)

FAKE_OUTPUT = "## Estimate: Sample Project\n\n1. Backend: 40 hours\n\n**Total: 40 hours**"
FAKE_RESPONSE_ID = "resp_abc123"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@dataclass
class _StreamUsage:
    input_tokens: int
    output_tokens: int
    output_tokens_details: Any | None = None


@dataclass
class _StreamResponse:
    id: str
    usage: _StreamUsage


@dataclass
class _StreamEvent:
    type: str
    delta: str | None = None
    response: _StreamResponse | None = None


async def _yield_openai_events(
    response: _StreamResponse,
    *,
    include_completed: bool = True,
) -> AsyncIterator[_StreamEvent]:
    yield _StreamEvent("response.output_text.delta", delta="Hello ")
    yield _StreamEvent("response.output_text.delta", delta="world")
    if include_completed:
        yield _StreamEvent("response.completed", response=response)

def _make_response_mock(
    output_text: str = FAKE_OUTPUT,
    status: str = "completed",
    input_tokens: int = 500,
    output_tokens: int = 200,
    response_id: str = FAKE_RESPONSE_ID,
    reasoning_tokens: int | None = None,
) -> MagicMock:
    """Build a minimal mock that mimics an OpenAI Responses API response object."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    if reasoning_tokens is not None:
        usage.output_tokens_details = MagicMock(reasoning_tokens=reasoning_tokens)
    else:
        usage.output_tokens_details = None

    response = MagicMock()
    response.status = status
    response.output_text = output_text
    response.usage = usage
    response.id = response_id
    return response


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def reset_client():
    """Reset the lazy OpenAI client singleton before every test."""
    openai_svc._client = None
    yield
    openai_svc._client = None


@pytest.fixture
def service() -> OpenAILLMService:
    """Fresh OpenAILLMService instance per test — state is always clean."""
    return OpenAILLMService()


# --------------------------------------------------------------------------- #
# _count_tokens — tiktoken-based
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

    def test_overhead_and_priming_are_included(self, service):
        """With two messages the overhead is 2*MSG_OVERHEAD + PRIMING_TOKENS."""
        enc = tiktoken.encoding_for_model(DEFAULT_MODEL)
        sys_text = "system"
        usr_text = "user"
        raw_tokens = len(enc.encode(sys_text)) + len(enc.encode(usr_text))
        expected = raw_tokens + 2 * _MSG_OVERHEAD + _PRIMING_TOKENS
        assert service._count_tokens(sys_text, usr_text, DEFAULT_MODEL) == expected

    def test_falls_back_to_cl100k_for_unknown_model(self, service):
        tokens = service._count_tokens("system", "user", model="unknown-model-xyz")
        assert tokens > 0


# --------------------------------------------------------------------------- #
# estimate — success path (standard model)
# --------------------------------------------------------------------------- #

class TestEstimateSuccess:
    @pytest.fixture
    def mock_response(self):
        return _make_response_mock()

    async def test_returns_dict(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert isinstance(result, dict)

    async def test_content_equals_output_text(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["estimation"] == FAKE_OUTPUT

    async def test_model_key_matches_resolved_model(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["model"] == DEFAULT_MODEL

    async def test_response_id_matches(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["response_id"] == FAKE_RESPONSE_ID

    async def test_token_counts_come_from_usage(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["input_tokens"] == mock_response.usage.input_tokens
        assert result["output_tokens"] == mock_response.usage.output_tokens

    async def test_reasoning_tokens_is_none_for_standard_model(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["reasoning_tokens"] is None

    async def test_turn_cost_is_positive_float(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert isinstance(result["turn_cost_usd"], float)
        assert result["turn_cost_usd"] > 0

    async def test_turn_cost_calculation(self, service, mock_response):
        info = MODELS[DEFAULT_MODEL]
        expected = round(
            (
                mock_response.usage.input_tokens * info["input_price"]
                + mock_response.usage.output_tokens * info["output_price"]
            )
            / 1_000_000,
            8,
        )
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["turn_cost_usd"] == expected

    async def test_estimated_precall_cost_is_positive(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert result["estimated_precall_cost_usd"] > 0

    async def test_estimated_input_tokens_is_positive_int(self, service, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert isinstance(result["estimated_input_tokens"], int)
        assert result["estimated_input_tokens"] > 0


# --------------------------------------------------------------------------- #
# _get_client — lazy singleton
# --------------------------------------------------------------------------- #


class TestGetClient:
    def test_client_is_cached(self, monkeypatch) -> None:
        class DummyClient:
            def __init__(self, api_key: str) -> None:
                self.api_key = api_key

        monkeypatch.setattr(openai_svc, "AsyncOpenAI", DummyClient)
        monkeypatch.setattr(settings, "openai_api_key", "test-key")
        openai_svc._client = None

        first = openai_svc._get_client()
        second = openai_svc._get_client()

        assert first is second
        assert first.api_key == "test-key"


# --------------------------------------------------------------------------- #
# _call_provider_stream — streaming
# --------------------------------------------------------------------------- #


class TestCallProviderStream:
    @pytest.mark.asyncio
    async def test_stream_emits_deltas_and_sets_partial(self, service: OpenAILLMService) -> None:
        response = _StreamResponse(
            id="resp_stream",
            usage=_StreamUsage(input_tokens=10, output_tokens=5),
        )
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                return_value=_yield_openai_events(response)
            )
            deltas: list[str] = []
            async for delta in service._call_provider_stream({"model": "gpt"}, is_reasoning=False):
                deltas.append(delta)

        assert "".join(deltas) == "Hello world"
        assert service._stream_partial["response_id"] == "resp_stream"
        assert service._stream_partial["input_tokens"] == 10

    @pytest.mark.asyncio
    async def test_stream_includes_reasoning_tokens(self, service: OpenAILLMService) -> None:
        details = MagicMock(reasoning_tokens=42)
        response = _StreamResponse(
            id="resp_stream",
            usage=_StreamUsage(input_tokens=10, output_tokens=5, output_tokens_details=details),
        )
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                return_value=_yield_openai_events(response)
            )
            async for _ in service._call_provider_stream({"model": "gpt"}, is_reasoning=True):
                pass

        assert service._stream_partial["reasoning_tokens"] == 42

    @pytest.mark.asyncio
    async def test_stream_raises_without_completed_event(self, service: OpenAILLMService) -> None:
        response = _StreamResponse(
            id="resp_stream",
            usage=_StreamUsage(input_tokens=10, output_tokens=5),
        )
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                return_value=_yield_openai_events(response, include_completed=False)
            )
            with pytest.raises(LLMServiceError) as exc_info:
                async for _ in service._call_provider_stream({"model": "gpt"}, is_reasoning=False):
                    pass

        assert exc_info.value.type == "stream_error"

    @pytest.mark.asyncio
    async def test_stream_maps_provider_errors(self, service: OpenAILLMService) -> None:
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                side_effect=AuthenticationError(message="bad key", response=MagicMock(), body={})
            )
            with pytest.raises(LLMServiceError) as exc_info:
                async for _ in service._call_provider_stream({"model": "gpt"}, is_reasoning=False):
                    pass

        assert exc_info.value.type == "authentication_error"


# --------------------------------------------------------------------------- #
# estimate — CAG: system prompt injection
# --------------------------------------------------------------------------- #

class TestEstimateSystemPrompt:
    async def test_instructions_contain_example_header(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Build something")

        call_kwargs = create_mock.call_args.kwargs
        assert EXAMPLE_HEADER_TEMPLATE.format(index=1) in call_kwargs["instructions"]

    async def test_input_param_equals_transcription(self, service):
        transcription = "Build a real-time chat application"
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate(transcription)

        call_kwargs = create_mock.call_args.kwargs
        assert call_kwargs["input"] == transcription

    async def test_model_param_sent_to_api(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Build something")

        assert create_mock.call_args.kwargs["model"] == DEFAULT_MODEL


# --------------------------------------------------------------------------- #
# estimate — PRE-CALL validation
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
        assert "overflow" in exc_info.value.type

    async def test_no_error_key_on_success(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build a simple API")
        assert "error" not in result


# --------------------------------------------------------------------------- #
# estimate — non-completed API status
# --------------------------------------------------------------------------- #

class TestEstimateApiErrors:
    async def test_raises_llm_service_error_when_status_is_not_completed(self, service):
        mock_response = _make_response_mock(status="failed")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("Build something")
        assert exc_info.value.type == "failed"

    async def test_error_has_message(self, service):
        mock_response = _make_response_mock(status="incomplete")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("Build something")
        assert exc_info.value.message


# --------------------------------------------------------------------------- #
# estimate — temperature / top_p routing
# --------------------------------------------------------------------------- #

class TestEstimateParamRouting:
    async def test_temperature_sent_when_provided(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", model="gpt-4o-mini", temperature=0.7)
        assert create_mock.call_args.kwargs.get("temperature") == 0.7

    async def test_top_p_sent_when_provided(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", model="gpt-4o-mini", top_p=0.9)
        assert create_mock.call_args.kwargs.get("top_p") == 0.9

    async def test_temperature_not_sent_when_omitted(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test")
        assert "temperature" not in create_mock.call_args.kwargs


# --------------------------------------------------------------------------- #
# estimate — parameters ignored by OpenAI (top_k, verbosity)
# --------------------------------------------------------------------------- #

class TestEstimateIgnoredParams:
    """top_k and verbosity are accepted by the base contract but have no meaning
    for the OpenAI Responses API.  They must be silently ignored — never
    forwarded to responses.create — and must never raise a TypeError."""

    async def test_top_k_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", top_k=40)
        assert "estimation" in result

    async def test_top_k_not_forwarded_to_api(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", top_k=40)
        assert "top_k" not in create_mock.call_args.kwargs

    async def test_verbosity_low_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", verbosity="low")
        assert "estimation" in result

    async def test_verbosity_medium_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", verbosity="medium")
        assert "estimation" in result

    async def test_verbosity_high_does_not_raise(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", verbosity="high")
        assert "estimation" in result

    async def test_verbosity_not_forwarded_to_api(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", verbosity="high")
        assert "verbosity" not in create_mock.call_args.kwargs

    async def test_top_k_and_verbosity_together_do_not_raise(self, service):
        """Both ignored params can be combined without conflict."""
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", top_k=50, verbosity="medium")
        assert "estimation" in result

    def test_build_api_params_accepts_top_k_keyword(self, service):
        """Direct call to _build_api_params with top_k must not raise TypeError."""
        resolved_model = DEFAULT_MODEL
        info = MODELS[resolved_model]
        params = service._build_api_params(
            resolved_model=resolved_model,
            system_prompt="system",
            transcription="user message",
            model_info=info,
            temperature=None,
            top_p=None,
            top_k=40,
            reasoning_effort="medium",
            verbosity="low",
            max_output_tokens=1024,
            continue_conversation=False,
        )
        assert "top_k" not in params
        assert "verbosity" not in params


# --------------------------------------------------------------------------- #
# estimate — multi-turn session state
# --------------------------------------------------------------------------- #

class TestEstimateMultiTurn:
    async def test_store_is_true_when_continue_conversation(self, service):
        mock_response = _make_response_mock(response_id="resp_turn1")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", continue_conversation=True)
        assert create_mock.call_args.kwargs.get("store") is True

    async def test_store_is_false_for_stateless_call(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", continue_conversation=False)
        assert create_mock.call_args.kwargs.get("store") is False

    async def test_previous_response_id_attached_on_second_turn(self, service):
        first_id = "resp_first"
        mock_response = _make_response_mock(response_id=first_id)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("turn 1", continue_conversation=True)
            await service.estimate("turn 2", continue_conversation=True)

        second_call_kwargs = create_mock.call_args_list[1].kwargs
        assert second_call_kwargs.get("previous_response_id") == first_id

    async def test_total_cost_accumulates_across_turns(self, service):
        mock_response = _make_response_mock(input_tokens=100, output_tokens=50)
        info = MODELS[DEFAULT_MODEL]
        turn_cost = (100 * info["input_price"] + 50 * info["output_price"]) / 1_000_000

        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("turn 1", continue_conversation=True)
            result = await service.estimate("turn 2", continue_conversation=True)

        assert abs(result["total_cost_usd"] - round(turn_cost * 2, 8)) < 1e-9

    async def test_stateless_total_cost_equals_turn_cost(self, service):
        mock_response = _make_response_mock(input_tokens=100, output_tokens=50)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", continue_conversation=False)
        assert result["total_cost_usd"] == result["turn_cost_usd"]

    async def test_reset_clears_session_state(self, service):
        mock_response = _make_response_mock(response_id="resp_turn1")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            await service.estimate("turn 1", continue_conversation=True)

        assert service._last_response_id == "resp_turn1"
        assert service._turn_count == 1
        assert service._total_cost > 0

        service.reset()

        assert service._last_response_id is None
        assert service._turn_count == 0
        assert service._total_cost == 0.0

    async def test_after_reset_no_previous_response_id_sent(self, service):
        mock_response = _make_response_mock(response_id="resp_turn1")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("turn 1", continue_conversation=True)
            service.reset()
            await service.estimate("new start", continue_conversation=True)

        second_call_kwargs = create_mock.call_args_list[1].kwargs
        assert "previous_response_id" not in second_call_kwargs


# --------------------------------------------------------------------------- #
# estimate — reasoning model (o4-mini)
# --------------------------------------------------------------------------- #

class TestEstimateReasoningModel:
    async def test_reasoning_param_sent_for_reasoning_model(self, service):
        mock_response = _make_response_mock(reasoning_tokens=80)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", model="o4-mini")
        assert "reasoning" in create_mock.call_args.kwargs

    async def test_temperature_not_sent_for_reasoning_model(self, service):
        mock_response = _make_response_mock(reasoning_tokens=80)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", model="o4-mini", temperature=0.7)
        assert "temperature" not in create_mock.call_args.kwargs

    async def test_reasoning_tokens_extracted_from_usage(self, service):
        mock_response = _make_response_mock(reasoning_tokens=80)
        mock_response.usage.output_tokens_details = MagicMock(reasoning_tokens=80)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("test", model="o4-mini")
        assert result["reasoning_tokens"] == 80

    async def test_text_format_sent_for_reasoning_model(self, service):
        mock_response = _make_response_mock(reasoning_tokens=50)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", model="o4-mini")
        text_param = create_mock.call_args.kwargs.get("text")
        assert text_param == {"format": {"type": "text"}}

    async def test_text_param_not_sent_for_non_reasoning_model(self, service):
        mock_response = _make_response_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await service.estimate("test", model="gpt-4o-mini")
        assert "text" not in create_mock.call_args.kwargs


# --------------------------------------------------------------------------- #
# estimate — provider exception handling
# --------------------------------------------------------------------------- #

class TestEstimateProviderExceptions:
    async def test_authentication_error_raises_401(self, service):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                side_effect=AuthenticationError(
                    message="Invalid key", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 401
        assert exc_info.value.type == "authentication_error"

    async def test_rate_limit_error_raises_429(self, service):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                side_effect=RateLimitError(
                    message="Rate limit", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 429
        assert exc_info.value.type == "rate_limit_error"

    async def test_bad_request_error_raises_400(self, service):
        exc = BadRequestError(message="Bad input", response=MagicMock(), body={})
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(side_effect=exc)
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 400
        assert exc_info.value.type == "bad_request_error"
        assert "Bad input" in exc_info.value.message

    async def test_connection_error_raises_503(self, service):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                side_effect=APIConnectionError(request=MagicMock())
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 503
        assert exc_info.value.type == "connection_error"

    async def test_internal_server_error_raises_503(self, service):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                side_effect=InternalServerError(
                    message="Server error", response=MagicMock(), body={}
                )
            )
            with pytest.raises(LLMServiceError) as exc_info:
                await service.estimate("test")
        assert exc_info.value.status_code == 503
        assert exc_info.value.type == "connection_error"


# --------------------------------------------------------------------------- #
# estimate — pre-call two-step flow
# --------------------------------------------------------------------------- #

FAKE_REQUIREMENTS = (
    "1. User authentication with JWT\n"
    "2. Product catalog with search\n"
    "3. Shopping cart and checkout\n"
)


class TestEstimatePreCall:
    """Tests for the optional pre-call step that extracts requirements from
    a raw transcription before the main estimation call."""

    def _make_pre_call_response(self) -> MagicMock:
        return _make_response_mock(
            output_text=FAKE_REQUIREMENTS,
            response_id="resp_pre_call",
            input_tokens=300,
            output_tokens=80,
        )

    def _make_estimation_response(self) -> MagicMock:
        return _make_response_mock(
            output_text=FAKE_OUTPUT,
            response_id="resp_estimation",
            input_tokens=400,
            output_tokens=200,
        )

    async def test_provider_called_twice_when_pre_call_enabled(self, service):
        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Raw long meeting transcription here", pre_call=True)
        assert create_mock.call_count == 2

    async def test_provider_called_once_when_pre_call_disabled(self, service):
        create_mock = AsyncMock(return_value=self._make_estimation_response())
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Build a simple API", pre_call=False)
        assert create_mock.call_count == 1

    async def test_requirements_key_contains_pre_call_output(self, service):
        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            result = await service.estimate("Raw transcription text here", pre_call=True)
        assert result["requirements"] == FAKE_REQUIREMENTS

    async def test_requirements_is_none_when_pre_call_disabled(self, service):
        create_mock = AsyncMock(return_value=self._make_estimation_response())
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            result = await service.estimate("Build a simple API", pre_call=False)
        assert result["requirements"] is None

    async def test_pre_call_cost_usd_is_set_when_pre_call_enabled(self, service):
        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            result = await service.estimate("Raw transcription text here", pre_call=True)
        assert result["pre_call_cost_usd"] is not None
        assert result["pre_call_cost_usd"] > 0

    async def test_pre_call_cost_usd_is_none_when_pre_call_disabled(self, service):
        create_mock = AsyncMock(return_value=self._make_estimation_response())
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            result = await service.estimate("Build a simple API", pre_call=False)
        assert result["pre_call_cost_usd"] is None

    async def test_total_cost_includes_pre_call_cost(self, service):
        pre_response = self._make_pre_call_response()
        est_response = self._make_estimation_response()
        info = MODELS[DEFAULT_MODEL]

        expected_pre_cost = (
            pre_response.usage.input_tokens * info["input_price"]
            + pre_response.usage.output_tokens * info["output_price"]
        ) / 1_000_000
        expected_est_cost = (
            est_response.usage.input_tokens * info["input_price"]
            + est_response.usage.output_tokens * info["output_price"]
        ) / 1_000_000
        expected_total = round(expected_pre_cost + expected_est_cost, 8)

        create_mock = AsyncMock(side_effect=[pre_response, est_response])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            result = await service.estimate("Raw transcription text here", pre_call=True)
        assert abs(result["total_cost_usd"] - expected_total) < 1e-9

    async def test_second_call_receives_requirements_as_input(self, service):
        """The estimation call must receive the extracted requirements, not the original transcription."""
        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Original raw transcription text", pre_call=True)

        second_call_kwargs = create_mock.call_args_list[1].kwargs
        assert second_call_kwargs["input"] == FAKE_REQUIREMENTS

    async def test_first_call_uses_pre_call_system_prompt(self, service):
        """The first call must NOT include the CAG examples header."""
        from app.context.examples import EXAMPLE_HEADER_TEMPLATE

        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Original raw transcription text", pre_call=True)

        first_call_instructions = create_mock.call_args_list[0].kwargs["instructions"]
        assert EXAMPLE_HEADER_TEMPLATE.format(index=1) not in first_call_instructions
        assert "requirements" in first_call_instructions.lower()

    async def test_second_call_uses_estimation_system_prompt(self, service):
        """The second call must include the CAG examples header."""
        from app.context.examples import EXAMPLE_HEADER_TEMPLATE

        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            await service.estimate("Original raw transcription text", pre_call=True)

        second_call_instructions = create_mock.call_args_list[1].kwargs["instructions"]
        assert EXAMPLE_HEADER_TEMPLATE.format(index=1) in second_call_instructions

    async def test_estimation_key_contains_main_call_output(self, service):
        """The 'estimation' key must come from the second call, not the pre-call."""
        create_mock = AsyncMock(side_effect=[
            self._make_pre_call_response(),
            self._make_estimation_response(),
        ])
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = create_mock
            result = await service.estimate("Raw transcription text here", pre_call=True)
        assert result["estimation"] == FAKE_OUTPUT
