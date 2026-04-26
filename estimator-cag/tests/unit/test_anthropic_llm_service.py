"""Unit tests for AnthropicLLMService — no facade, no OpenAI dependency."""
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
from app.services.anthropic_llm_service import (
    DEFAULT_MODEL,
    MODELS,
    _CHARS_PER_TOKEN,
    AnthropicLLMService,
)

FAKE_OUTPUT = "## Estimate: E-commerce Platform\n\n1. Backend: 60 hours\n\n**Total: 60 hours**"
FAKE_RESPONSE_ID = "msg_abc123"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_response_mock(
    output_text: str = FAKE_OUTPUT,
    stop_reason: str = "end_turn",
    input_tokens: int = 500,
    output_tokens: int = 200,
    response_id: str = FAKE_RESPONSE_ID,
) -> MagicMock:
    """Build a minimal mock that mimics an Anthropic Messages API response object."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    content_block = MagicMock()
    content_block.text = output_text

    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = [content_block]
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
        # total_chars = 700, 700 / 3.5 = 200
        expected = int(700 / _CHARS_PER_TOKEN)
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
        assert result["content"] == FAKE_OUTPUT

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

    async def test_reasoning_tokens_is_always_none(self, service, mock_response):
        """Anthropic does not expose reasoning tokens."""
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
                mock_response.usage.input_tokens * info["input_price"]
                + mock_response.usage.output_tokens * info["output_price"]
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
        assert result.get("content") == FAKE_OUTPUT

    async def test_non_truncated_response_has_truncated_false(self, service):
        mock_response = _make_response_mock(stop_reason="end_turn")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build something")
        assert result.get("truncated") is False

    async def test_unknown_stop_reason_returns_error_dict(self, service):
        mock_response = _make_response_mock(stop_reason="tool_use")
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await service.estimate("Build something")
        assert result.get("error") is True
        assert result.get("type") == "tool_use"
        assert "message" in result


# --------------------------------------------------------------------------- #
# estimate — provider exception handling
# --------------------------------------------------------------------------- #

class TestEstimateProviderExceptions:
    async def test_authentication_error_returns_401(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=AuthenticationError(
                    message="Invalid key", response=MagicMock(), body={}
                )
            )
            result = await service.estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 401
        assert result.get("type") == "authentication_error"

    async def test_rate_limit_error_returns_429(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=RateLimitError(
                    message="Rate limit", response=MagicMock(), body={}
                )
            )
            result = await service.estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 429
        assert result.get("type") == "rate_limit_error"

    async def test_bad_request_error_returns_400(self, service):
        exc = BadRequestError(message="Bad input", response=MagicMock(), body={})
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(side_effect=exc)
            result = await service.estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 400
        assert result.get("type") == "bad_request_error"
        assert "Bad input" in result.get("message", "")

    async def test_connection_error_returns_503(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=APIConnectionError(request=MagicMock())
            )
            result = await service.estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 503
        assert result.get("type") == "connection_error"

    async def test_internal_server_error_returns_503(self, service):
        with patch("app.services.anthropic_llm_service._get_client") as mock_client:
            mock_client.return_value.messages.create = AsyncMock(
                side_effect=InternalServerError(
                    message="Server error", response=MagicMock(), body={}
                )
            )
            result = await service.estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 503
        assert result.get("type") == "connection_error"


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
# estimate — PRE-CALL validation (inherited from BaseLLMService)
# --------------------------------------------------------------------------- #

class TestEstimateValidation:
    async def test_raises_when_both_temperature_and_top_p_set(self, service):
        with pytest.raises(ValueError, match="mutually exclusive"):
            await service.estimate("test", temperature=0.5, top_p=0.9)

    async def test_raises_when_model_not_in_registry(self, service):
        with pytest.raises(ValueError, match="Unknown model"):
            await service.estimate("test", model="nonexistent-model")

    async def test_returns_error_dict_on_context_overflow(self, service):
        with patch.object(service, "_count_tokens", return_value=999_999_999):
            result = await service.estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 413
        assert "overflow" in result.get("type", "")
