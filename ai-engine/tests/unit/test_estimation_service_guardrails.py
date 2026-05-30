"""Unit tests for guardrail integration inside EstimationService.

These tests verify that:
  - check_input is called exactly once per public method (estimate, estimate_stream,
    estimate_structured) with the request's transcription.
  - When check_input raises InputGuardrailViolation the service propagates it
    without wrapping or swallowing it.
  - When check_input passes, the LLM path is invoked normally.

LiteLLM and the OpenAI moderation client are both mocked so no network call is made.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.guardrails.input import InputGuardrailViolation
from app.schemas.estimation import EstimationRequest
from app.schemas.llm import LLMObservableResponse, LLMUsage
from app.services.estimation_service import EstimationService

# Minimum-valid transcription (>= 50 chars)
VALID_TRANSCRIPTION = "Build a web SaaS platform with user authentication and a reporting dashboard."

_ESTIMATION_REQUEST = EstimationRequest(transcription=VALID_TRANSCRIPTION)


def _make_litellm_response(content: str = "## Estimate\nTotal: 100h") -> LLMObservableResponse:
    return LLMObservableResponse(
        model="gpt-4o-mini",
        content=content,
        usage=LLMUsage(
            prompt_tokens=400,
            completion_tokens=150,
            total_tokens=550,
        ),
        latency_ms=120.0,
        cost_usd=Decimal("0.0008"),
        response_id="resp-unit-guardrail-001",
    )


# ---------------------------------------------------------------------------
# estimate() — guardrail fires before LLM
# ---------------------------------------------------------------------------

class TestEstimateGuardrails:
    async def test_violation_propagates(self):
        violation = InputGuardrailViolation("Email detected.", reason="pii")
        with patch(
            "app.services.estimation_service.check_input",
            side_effect=violation,
        ):
            svc = EstimationService()
            with pytest.raises(InputGuardrailViolation) as exc_info:
                await svc.estimate(_ESTIMATION_REQUEST)
        assert exc_info.value.reason == "pii"

    async def test_check_input_called_with_transcription(self):
        mock_check = MagicMock()
        mock_resp = _make_litellm_response()
        with (
            patch("app.services.estimation_service.check_input", mock_check),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=mock_resp),
            ),
            patch("app.services.estimation_service._get_moderation_client", return_value=None),
        ):
            svc = EstimationService()
            await svc.estimate(_ESTIMATION_REQUEST)

        mock_check.assert_called_once()
        args, kwargs = mock_check.call_args
        assert args[0] == VALID_TRANSCRIPTION

    async def test_llm_not_called_when_guardrail_raises(self):
        violation = InputGuardrailViolation("Injection detected.", reason="prompt_injection")
        with (
            patch("app.services.estimation_service.check_input", side_effect=violation),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
            ) as mock_complete,
        ):
            svc = EstimationService()
            with pytest.raises(InputGuardrailViolation):
                await svc.estimate(_ESTIMATION_REQUEST)

        mock_complete.assert_not_called()


# ---------------------------------------------------------------------------
# estimate_stream() — guardrail fires before streaming
# ---------------------------------------------------------------------------

class TestEstimateStreamGuardrails:
    async def test_violation_propagates(self):
        violation = InputGuardrailViolation("PII detected.", reason="pii")
        with patch(
            "app.services.estimation_service.check_input",
            side_effect=violation,
        ):
            svc = EstimationService()
            with pytest.raises(InputGuardrailViolation) as exc_info:
                # Must consume the async generator to trigger the guardrail
                async for _ in svc.estimate_stream(_ESTIMATION_REQUEST):
                    pass
        assert exc_info.value.reason == "pii"

    async def test_check_input_called_with_transcription(self):
        mock_check = MagicMock()

        async def _fake_stream(*args, **kwargs):
            yield "some"
            yield " text"

        with (
            patch("app.services.estimation_service.check_input", mock_check),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.stream",
                new=_fake_stream,
            ),
            patch("app.services.estimation_service._get_moderation_client", return_value=None),
        ):
            svc = EstimationService()
            async for _ in svc.estimate_stream(_ESTIMATION_REQUEST):
                pass

        mock_check.assert_called_once()
        args, _ = mock_check.call_args
        assert args[0] == VALID_TRANSCRIPTION


# ---------------------------------------------------------------------------
# estimate_structured() — guardrail fires before structured LLM call
# ---------------------------------------------------------------------------

class TestEstimateStructuredGuardrails:
    async def test_violation_propagates(self):
        violation = InputGuardrailViolation("Moderation flagged.", reason="moderation")
        with patch(
            "app.services.estimation_service.check_input",
            side_effect=violation,
        ):
            svc = EstimationService()
            with pytest.raises(InputGuardrailViolation) as exc_info:
                await svc.estimate_structured(_ESTIMATION_REQUEST)
        assert exc_info.value.reason == "moderation"

    async def test_check_input_called_with_transcription(self):
        from app.schemas.estimation import EstimationResult

        mock_check = MagicMock()
        fake_result = MagicMock(spec=EstimationResult)
        fake_result.phases = []
        fake_result.summary = "Test"
        fake_result.total_duration_weeks = 4
        fake_result.total_cost_eur = 0
        fake_result.confidence_pct = 80

        fake_completion = LLMObservableResponse(
            model="gpt-4o-mini",
            content="Estimate text",
            usage=LLMUsage(
                prompt_tokens=300,
                completion_tokens=100,
                total_tokens=400,
            ),
            latency_ms=300.0,
            cost_usd=Decimal("0.005"),
            response_id="resp-structured-001",
        )

        with (
            patch("app.services.estimation_service.check_input", mock_check),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(return_value=(fake_result, fake_completion)),
            ),
            patch("app.services.estimation_service._get_moderation_client", return_value=None),
        ):
            svc = EstimationService()
            await svc.estimate_structured(_ESTIMATION_REQUEST)

        mock_check.assert_called_once()
        args, _ = mock_check.call_args
        assert args[0] == VALID_TRANSCRIPTION
