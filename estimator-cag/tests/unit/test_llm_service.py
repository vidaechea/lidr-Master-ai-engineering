from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.openai_llm_service as svc
from app.context.examples import EXAMPLE_HEADER_TEMPLATE
from app.services.openai_llm_service import (
    DEFAULT_MODEL,
    MODELS,
    _MSG_OVERHEAD,
    _PRIMING_TOKENS,
    estimate,
    estimate_call_tokens,
)

FAKE_OUTPUT = "## Estimate: Sample Project\n\n1. Backend: 40 hours\n\n**Total: 40 hours**"
FAKE_RESPONSE_ID = "resp_abc123"


def _make_responses_mock(
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


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset OpenAI client and singleton session state before every test."""
    svc._client = None
    svc._openai_service._last_response_id = None
    svc._openai_service._turn_count = 0
    svc._openai_service._total_cost = 0.0
    yield


# --------------------------------------------------------------------------- #
# estimate_call_tokens — pure function, no mock needed
# --------------------------------------------------------------------------- #
class TestEstimateCallTokens:
    def test_returns_positive_integer(self):
        tokens = estimate_call_tokens("You are an expert.", "Build a CRUD app.")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_longer_inputs_produce_more_tokens(self):
        short = estimate_call_tokens("system", "short")
        long = estimate_call_tokens("system", "short " * 200)
        assert long > short

    def test_overhead_and_priming_are_included(self):
        """With two messages the overhead is 2*MSG_OVERHEAD + PRIMING_TOKENS."""
        import tiktoken

        enc = tiktoken.encoding_for_model(DEFAULT_MODEL)
        sys_text = "system"
        usr_text = "user"
        raw_tokens = len(enc.encode(sys_text)) + len(enc.encode(usr_text))
        expected = raw_tokens + 2 * _MSG_OVERHEAD + _PRIMING_TOKENS
        assert estimate_call_tokens(sys_text, usr_text) == expected

    def test_falls_back_to_cl100k_for_unknown_model(self):
        tokens = estimate_call_tokens("system", "user", model="unknown-model-xyz")
        assert tokens > 0


# --------------------------------------------------------------------------- #
# estimate — success path (standard model)
# --------------------------------------------------------------------------- #
class TestEstimateSuccess:
    @pytest.fixture
    def mock_response(self):
        return _make_responses_mock()

    async def test_returns_dict(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert isinstance(result, dict)

    async def test_content_equals_output_text(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert result["content"] == FAKE_OUTPUT

    async def test_model_key_matches_resolved_model(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert result["model"] == DEFAULT_MODEL

    async def test_response_id_matches(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert result["response_id"] == FAKE_RESPONSE_ID

    async def test_token_counts_come_from_usage(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert result["input_tokens"] == mock_response.usage.input_tokens
        assert result["output_tokens"] == mock_response.usage.output_tokens

    async def test_reasoning_tokens_is_none_for_standard_model(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert result["reasoning_tokens"] is None

    async def test_turn_cost_is_positive_float(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert isinstance(result["turn_cost_usd"], float)
        assert result["turn_cost_usd"] > 0

    async def test_turn_cost_calculation(self, mock_response):
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
            result = await estimate("Build a simple API")
        assert result["turn_cost_usd"] == expected

    async def test_estimated_precall_cost_is_positive(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert result["estimated_precall_cost_usd"] > 0

    async def test_estimated_input_tokens_is_positive_int(self, mock_response):
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert isinstance(result["estimated_input_tokens"], int)
        assert result["estimated_input_tokens"] > 0


# --------------------------------------------------------------------------- #
# estimate — CAG: system prompt injection
# --------------------------------------------------------------------------- #
class TestEstimateSystemPrompt:
    async def test_instructions_contain_example_header(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("Build something")

        call_kwargs = create_mock.call_args.kwargs
        assert EXAMPLE_HEADER_TEMPLATE.format(index=1) in call_kwargs["instructions"]

    async def test_input_param_equals_transcription(self):
        transcription = "Build a real-time chat application"
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate(transcription)

        call_kwargs = create_mock.call_args.kwargs
        assert call_kwargs["input"] == transcription

    async def test_model_param_sent_to_api(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("Build something")

        assert create_mock.call_args.kwargs["model"] == DEFAULT_MODEL


# --------------------------------------------------------------------------- #
# estimate — PRE-CALL validation
# --------------------------------------------------------------------------- #
class TestEstimateValidation:
    async def test_raises_when_both_temperature_and_top_p_set(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            await estimate("test", temperature=0.5, top_p=0.9)

    async def test_raises_when_model_not_in_registry(self):
        with pytest.raises(ValueError, match="Unknown model"):
            await estimate("test", model="nonexistent-model")

    async def test_returns_error_dict_on_context_overflow(self):
        with patch.object(svc._openai_service, "_count_tokens", return_value=999_999_999):
            result = await estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 413
        assert "context_overflow" in result.get("type", "")

    async def test_no_error_key_on_success(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build a simple API")
        assert "error" not in result


# --------------------------------------------------------------------------- #
# estimate — non-completed API status
# --------------------------------------------------------------------------- #
class TestEstimateApiErrors:
    async def test_returns_error_dict_when_status_is_not_completed(self):
        mock_response = _make_responses_mock(status="failed")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build something")
        assert result.get("error") is True
        assert result.get("type") == "failed"

    async def test_error_dict_contains_message(self):
        mock_response = _make_responses_mock(status="incomplete")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("Build something")
        assert "message" in result


# --------------------------------------------------------------------------- #
# estimate — temperature / top_p routing
# --------------------------------------------------------------------------- #
class TestEstimateParamRouting:
    async def test_temperature_sent_when_provided(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test", temperature=0.7)
        assert create_mock.call_args.kwargs.get("temperature") == 0.7

    async def test_top_p_sent_when_provided(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test", top_p=0.9)
        assert create_mock.call_args.kwargs.get("top_p") == 0.9

    async def test_temperature_not_sent_when_omitted(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test")
        assert "temperature" not in create_mock.call_args.kwargs


# --------------------------------------------------------------------------- #
# estimate — multi-turn session state
# --------------------------------------------------------------------------- #
class TestEstimateMultiTurn:
    async def test_store_is_true_when_continue_conversation(self):
        mock_response = _make_responses_mock(response_id="resp_turn1")
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test", continue_conversation=True)
        assert create_mock.call_args.kwargs.get("store") is True

    async def test_store_is_false_for_stateless_call(self):
        mock_response = _make_responses_mock()
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test", continue_conversation=False)
        assert create_mock.call_args.kwargs.get("store") is False

    async def test_previous_response_id_attached_on_second_turn(self):
        first_id = "resp_first"
        mock_response = _make_responses_mock(response_id=first_id)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            # First turn
            await estimate("turn 1", continue_conversation=True)
            # Second turn — previous_response_id must be attached
            await estimate("turn 2", continue_conversation=True)

        second_call_kwargs = create_mock.call_args_list[1].kwargs
        assert second_call_kwargs.get("previous_response_id") == first_id

    async def test_total_cost_accumulates_across_turns(self):
        mock_response = _make_responses_mock(input_tokens=100, output_tokens=50)
        info = MODELS[DEFAULT_MODEL]
        turn_cost = (100 * info["input_price"] + 50 * info["output_price"]) / 1_000_000

        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("turn 1", continue_conversation=True)
            result = await estimate("turn 2", continue_conversation=True)

        assert abs(result["total_cost_usd"] - round(turn_cost * 2, 8)) < 1e-9

    async def test_stateless_total_cost_equals_turn_cost(self):
        mock_response = _make_responses_mock(input_tokens=100, output_tokens=50)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("test", continue_conversation=False)
        assert result["total_cost_usd"] == result["turn_cost_usd"]


# --------------------------------------------------------------------------- #
# estimate — reasoning model (o4-mini)
# --------------------------------------------------------------------------- #
class TestEstimateReasoningModel:
    async def test_reasoning_param_sent_for_reasoning_model(self):
        mock_response = _make_responses_mock(reasoning_tokens=80)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test", model="o4-mini")
        assert "reasoning" in create_mock.call_args.kwargs

    async def test_temperature_not_sent_for_reasoning_model(self):
        mock_response = _make_responses_mock(reasoning_tokens=80)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            create_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.responses.create = create_mock
            await estimate("test", model="o4-mini", temperature=0.7)
        assert "temperature" not in create_mock.call_args.kwargs

    async def test_reasoning_tokens_extracted_from_usage(self):
        mock_response = _make_responses_mock(reasoning_tokens=80)
        mock_response.usage.output_tokens_details = MagicMock(reasoning_tokens=80)
        with patch("app.services.openai_llm_service._get_client") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_response)
            result = await estimate("test", model="o4-mini")
        assert result["reasoning_tokens"] == 80
