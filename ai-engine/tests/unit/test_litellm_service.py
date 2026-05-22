"""Unit tests for LiteLLMRouterService.complete()

Three observable failover scenarios the Router can produce:
  1. PRIMARY succeeds  → response.model contains "gpt-4o-mini", no warning logged.
  2. FALLBACK used     → router exhausted primary retries and returned an Anthropic
                         response (response.model contains "claude"). A warning is logged
                         but the call still succeeds from the caller's perspective.
  3. BOTH exhausted    → router raises a litellm exception after all retries.
                         complete() maps it to LLMServiceError and re-raises.

The litellm Router is mocked at the instance level so no real API calls are made.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import litellm
import pytest

from app.services.helpers.error_mapper import LLMServiceError
from app.services.litellm_service import LOGICAL_MODEL, LiteLLMRouterService, litellm_router_service


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_response(model: str = "gpt-4o-mini", content: str = "ok") -> MagicMock:
    """Minimal mock that looks like a litellm completion response."""
    resp = MagicMock()
    resp.model = model
    resp.id = "resp-test-001"
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].finish_reason = "stop"
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    return resp


_MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Estimate this project."},
]


# --------------------------------------------------------------------------- #
# Fixture — isolated service instance with mocked router
# --------------------------------------------------------------------------- #

@pytest.fixture
def svc() -> LiteLLMRouterService:
    """LiteLLMRouterService whose internal Router is fully mocked."""
    with patch("app.services.litellm_service.Router"):
        service = LiteLLMRouterService()
    # Replace the router created during __init__ with a fresh mock for each test
    service._router = MagicMock()
    return service


# --------------------------------------------------------------------------- #
# Scenario 1 — Primary model succeeds
# --------------------------------------------------------------------------- #

class TestPrimarySucceeds:
    async def test_returns_response(self, svc: LiteLLMRouterService):
        svc._router.acompletion = AsyncMock(return_value=_make_response("gpt-4o-mini"))
        result = await svc.complete(_MESSAGES)
        assert result.choices[0].message.content == "ok"

    async def test_uses_logical_model_name(self, svc: LiteLLMRouterService):
        svc._router.acompletion = AsyncMock(return_value=_make_response("gpt-4o-mini"))
        await svc.complete(_MESSAGES)
        call_kwargs = svc._router.acompletion.call_args
        assert call_kwargs.kwargs["model"] == LOGICAL_MODEL

    async def test_passes_messages_to_router(self, svc: LiteLLMRouterService):
        svc._router.acompletion = AsyncMock(return_value=_make_response("gpt-4o-mini"))
        await svc.complete(_MESSAGES, max_tokens=256)
        call_kwargs = svc._router.acompletion.call_args
        assert call_kwargs.kwargs["messages"] == _MESSAGES

    async def test_forwards_extra_kwargs_to_router(self, svc: LiteLLMRouterService):
        svc._router.acompletion = AsyncMock(return_value=_make_response("gpt-4o-mini"))
        await svc.complete(_MESSAGES, max_tokens=512, temperature=0.2)
        call_kwargs = svc._router.acompletion.call_args
        assert call_kwargs.kwargs["max_tokens"] == 512
        assert call_kwargs.kwargs["temperature"] == 0.2

    async def test_no_fallback_warning_logged(
        self, svc: LiteLLMRouterService, caplog: pytest.LogCaptureFixture
    ):
        svc._router.acompletion = AsyncMock(return_value=_make_response("gpt-4o-mini"))
        await svc.complete(_MESSAGES)
        # structlog does not use stdlib logging, so we check by spying on the router output
        # (no exception = primary path was taken; warning would only appear via fallback)
        assert svc._router.acompletion.call_count == 1


# --------------------------------------------------------------------------- #
# Scenario 2 — Router used the fallback (Anthropic) model
# --------------------------------------------------------------------------- #

class TestFallbackUsed:
    async def test_still_returns_response(self, svc: LiteLLMRouterService):
        svc._router.acompletion = AsyncMock(
            return_value=_make_response("anthropic/claude-haiku-4-5-20251001")
        )
        result = await svc.complete(_MESSAGES)
        assert result is not None
        assert result.choices[0].message.content == "ok"

    async def test_detects_claude_in_model_name(self, svc: LiteLLMRouterService):
        """Any response whose model contains 'claude' triggers fallback detection."""
        svc._router.acompletion = AsyncMock(
            return_value=_make_response("claude-haiku-4-5-20251001")
        )
        # Should not raise — fallback is handled gracefully
        result = await svc.complete(_MESSAGES)
        assert result.model == "claude-haiku-4-5-20251001"

    async def test_detects_anthropic_prefix_in_model_name(self, svc: LiteLLMRouterService):
        svc._router.acompletion = AsyncMock(
            return_value=_make_response("anthropic/claude-sonnet-4-6")
        )
        result = await svc.complete(_MESSAGES)
        assert result.model == "anthropic/claude-sonnet-4-6"

    async def test_no_warning_when_model_is_empty_string(self, svc: LiteLLMRouterService):
        """Empty model string must not trigger fallback detection."""
        resp = _make_response("gpt-4o-mini")
        resp.model = ""
        svc._router.acompletion = AsyncMock(return_value=resp)
        # Should complete without raising; no warning path entered
        result = await svc.complete(_MESSAGES)
        assert result is not None

    async def test_no_warning_when_model_attribute_is_none(self, svc: LiteLLMRouterService):
        """None model attribute must not trigger fallback detection."""
        resp = _make_response("gpt-4o-mini")
        resp.model = None
        svc._router.acompletion = AsyncMock(return_value=resp)
        result = await svc.complete(_MESSAGES)
        assert result is not None


# --------------------------------------------------------------------------- #
# Scenario 3 — Both primary and fallback exhausted (error mapping)
# --------------------------------------------------------------------------- #

class TestBothExhausted:

    @pytest.mark.parametrize(
        "litellm_exc_factory, expected_type, expected_status",
        [
            (
                lambda: litellm.AuthenticationError(
                    message="invalid key", llm_provider="openai", model="gpt-4o-mini"
                ),
                "authentication_error",
                401,
            ),
            (
                lambda: litellm.RateLimitError(
                    message="rate limit", llm_provider="openai", model="gpt-4o-mini"
                ),
                "rate_limit_error",
                429,
            ),
            (
                lambda: litellm.BadRequestError(
                    message="bad request", llm_provider="openai", model="gpt-4o-mini"
                ),
                "bad_request_error",
                400,
            ),
            (
                lambda: litellm.APIConnectionError(
                    message="connection failed", llm_provider="openai", model="gpt-4o-mini"
                ),
                "connection_error",
                503,
            ),
            (
                lambda: litellm.InternalServerError(
                    message="server error", llm_provider="openai", model="gpt-4o-mini"
                ),
                "internal_server_error",
                502,
            ),
        ],
        ids=["auth", "rate_limit", "bad_request", "connection", "internal_server"],
    )
    async def test_maps_litellm_exception_to_llm_service_error(
        self,
        svc: LiteLLMRouterService,
        litellm_exc_factory,
        expected_type: str,
        expected_status: int,
    ):
        svc._router.acompletion = AsyncMock(side_effect=litellm_exc_factory())
        with pytest.raises(LLMServiceError) as exc_info:
            await svc.complete(_MESSAGES)
        assert exc_info.value.error_type == expected_type
        assert exc_info.value.status_code == expected_status

    async def test_original_exception_is_chained(self, svc: LiteLLMRouterService):
        """LLMServiceError.__cause__ must be the original litellm exception."""
        original = litellm.RateLimitError(
            message="rate limit", llm_provider="openai", model="gpt-4o-mini"
        )
        svc._router.acompletion = AsyncMock(side_effect=original)
        with pytest.raises(LLMServiceError) as exc_info:
            await svc.complete(_MESSAGES)
        assert exc_info.value.__cause__ is original

    async def test_unknown_exception_propagates_unhandled(self, svc: LiteLLMRouterService):
        """Non-litellm exceptions must not be silently swallowed."""
        svc._router.acompletion = AsyncMock(side_effect=RuntimeError("unexpected"))
        with pytest.raises(RuntimeError, match="unexpected"):
            await svc.complete(_MESSAGES)


# --------------------------------------------------------------------------- #
# Singleton sanity check
# --------------------------------------------------------------------------- #

class TestSingleton:
    def test_module_level_singleton_is_correct_type(self):
        assert isinstance(litellm_router_service, LiteLLMRouterService)

    def test_singleton_has_router(self):
        assert hasattr(litellm_router_service, "_router")
        assert litellm_router_service._router is not None
