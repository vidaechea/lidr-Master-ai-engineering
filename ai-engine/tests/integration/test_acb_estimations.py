"""Integration tests for POST /api/v1/estimate/acb.

Tests the full HTTP request/response cycle using the FastAPI TestClient,
patching LiteLLM at the service layer to avoid real API calls.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas.estimation import (
    BossAction,
    BossDecision,
    CriticFeedback,
    CriticIssue,
    IssueCategory,
    IssueSeverity,
)

VALID_TRANSCRIPTION = (
    "Build a multi-tenant SaaS billing platform with Stripe integration, "
    "role-based access control, and a real-time dashboard."
)

VALID_PAYLOAD = {
    "transcription": VALID_TRANSCRIPTION,
    "max_iterations": 1,
}

FAKE_ACTOR_OUTPUT = (
    "## Software Estimate\n\n"
    "### Phase 1: Backend API — 120 h\n"
    "### Phase 2: Frontend — 80 h\n\n"
    "**Total: 200 h / 160 000 EUR**"
)


def _make_actor_mock(content: str = FAKE_ACTOR_OUTPUT) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = 500
    usage.completion_tokens = 220
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.id = "actor-integ-001"
    return resp


def _make_completion_mock(in_tok: int = 120, out_tok: int = 60) -> MagicMock:
    completion = MagicMock()
    completion.usage.prompt_tokens = in_tok
    completion.usage.completion_tokens = out_tok
    completion.id = "structured-integ-001"
    return completion


def _approved_critic() -> CriticFeedback:
    return CriticFeedback(
        issues=[],
        overall_assessment="Estimate is consistent and complete.",
        approved=True,
    )


def _accept_decision() -> BossDecision:
    return BossDecision(action=BossAction.ACCEPT, reasoning="No issues found.")


def _patch_acb(
    actor_response: MagicMock | None = None,
    critic_boss_side_effect: list | None = None,
):
    """Return a context manager tuple that mocks check_input + actor + structured."""
    actor_response = actor_response or _make_actor_mock()
    completion = _make_completion_mock()
    critic_boss_side_effect = critic_boss_side_effect or [
        (_approved_critic(), completion),
        (_accept_decision(), completion),
    ]

    ctx_check = patch("app.services.acb_service.check_input")
    ctx_moderation = patch("app.services.acb_service._get_moderation_client", return_value=None)
    ctx_complete = patch(
        "app.services.litellm_service.LiteLLMRouterService.complete",
        AsyncMock(return_value=actor_response),
    )
    ctx_structured = patch(
        "app.services.litellm_service.LiteLLMRouterService.complete_structured",
        AsyncMock(side_effect=critic_boss_side_effect),
    )
    return ctx_check, ctx_moderation, ctx_complete, ctx_structured


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate/acb — happy path
# --------------------------------------------------------------------------- #
class TestAcbEstimationHappyPath:
    def test_returns_200(self, client: TestClient):
        with _patch_acb()[0], _patch_acb()[1], _patch_acb()[2], _patch_acb()[3]:
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)
        assert response.status_code == 200

    def test_response_has_estimation_text(self, client: TestClient):
        ctx = _patch_acb()
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)
        data = response.json()
        assert "estimation" in data
        assert len(data["estimation"]) > 0

    def test_response_has_iterations_list(self, client: TestClient):
        ctx = _patch_acb()
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)
        data = response.json()
        assert "iterations" in data
        assert isinstance(data["iterations"], list)
        assert len(data["iterations"]) >= 1

    def test_response_has_final_decision(self, client: TestClient):
        ctx = _patch_acb()
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)
        data = response.json()
        assert "final_decision" in data
        assert data["final_decision"]["action"] == "accept"

    def test_response_has_token_counts(self, client: TestClient):
        ctx = _patch_acb()
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)
        data = response.json()
        assert data["acb_total_input_tokens"] > 0
        assert data["acb_total_output_tokens"] > 0


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate/acb — validation errors
# --------------------------------------------------------------------------- #
class TestAcbEstimationValidation:
    def test_missing_transcription_returns_422(self, client: TestClient):
        response = client.post("/api/v1/estimate/acb", json={"max_iterations": 1})
        assert response.status_code == 422

    def test_short_transcription_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/estimate/acb",
            json={"transcription": "Too short.", "max_iterations": 1},
        )
        assert response.status_code == 422

    def test_max_iterations_above_limit_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/estimate/acb",
            json={"transcription": VALID_TRANSCRIPTION, "max_iterations": 10},
        )
        assert response.status_code == 422

    def test_max_iterations_negative_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/estimate/acb",
            json={"transcription": VALID_TRANSCRIPTION, "max_iterations": -1},
        )
        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate/acb — guardrail violations
# --------------------------------------------------------------------------- #
class TestAcbEstimationGuardrails:
    def test_pii_email_returns_422(self, client: TestClient):
        from app.guardrails.input import InputGuardrailViolation

        with patch(
            "app.services.acb_service.check_input",
            side_effect=InputGuardrailViolation("PII detected.", reason="pii"),
        ):
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)

        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "pii"

    def test_prompt_injection_returns_422(self, client: TestClient):
        from app.guardrails.input import InputGuardrailViolation

        with patch(
            "app.services.acb_service.check_input",
            side_effect=InputGuardrailViolation("Injection.", reason="prompt_injection"),
        ):
            response = client.post("/api/v1/estimate/acb", json=VALID_PAYLOAD)

        assert response.status_code == 422
