from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.estimation_service import _apply_ai_response, apply_callback


class _FakeEstimation:
    """Minimal stand-in for Estimation ORM model — no DB required."""

    estimation_markdown = None
    model_used = None
    input_tokens = None
    output_tokens = None
    turn_cost_usd = None
    total_cost_usd = None
    requirements = None
    validation_result = None
    structured_result = None
    prompt_version = None
    status = "processing"
    error_detail = None
    completed_at = None


_FULL_AI_RESPONSE = {
    "estimation": "## Admin Portal\n1. Auth & SSO: 40h\n**Total: 40h**",
    "model": "gpt-4o-mini",
    "input_tokens": 450,
    "output_tokens": 180,
    "turn_cost_usd": 0.00060,
    "total_cost_usd": 0.00060,
    "requirements": "- SSO\n- User list\n- Audit log",
    "validation": {"warnings": []},
    "structured_result": {"phases": [{"name": "Auth & SSO", "hours": 40}]},
    "prompt_version": "v1",
}


class TestApplyAiResponse:
    def test_sets_estimation_markdown(self):
        est = _FakeEstimation()
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.estimation_markdown == _FULL_AI_RESPONSE["estimation"]

    def test_sets_model_used(self):
        est = _FakeEstimation()
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.model_used == "gpt-4o-mini"

    def test_sets_token_counts(self):
        est = _FakeEstimation()
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.input_tokens == 450
        assert est.output_tokens == 180

    def test_sets_costs(self):
        est = _FakeEstimation()
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.turn_cost_usd == pytest.approx(0.00060)
        assert est.total_cost_usd == pytest.approx(0.00060)

    def test_sets_requirements_and_validation(self):
        est = _FakeEstimation()
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.requirements == _FULL_AI_RESPONSE["requirements"]
        assert est.validation_result == _FULL_AI_RESPONSE["validation"]

    def test_sets_structured_result(self):
        est = _FakeEstimation()
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.structured_result == _FULL_AI_RESPONSE["structured_result"]

    def test_does_not_override_existing_prompt_version(self):
        est = _FakeEstimation()
        est.prompt_version = "v2"
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.prompt_version == "v2"

    def test_sets_prompt_version_when_none(self):
        est = _FakeEstimation()
        est.prompt_version = None
        _apply_ai_response(est, _FULL_AI_RESPONSE)
        assert est.prompt_version == "v1"

    def test_handles_partial_response_without_error(self):
        est = _FakeEstimation()
        _apply_ai_response(est, {"estimation": "short estimate"})
        assert est.estimation_markdown == "short estimate"
        assert est.model_used is None
        assert est.input_tokens is None

    def test_handles_empty_response_without_error(self):
        est = _FakeEstimation()
        _apply_ai_response(est, {})
        assert est.estimation_markdown is None
        assert est.model_used is None


class TestApplyCallback:
    async def test_completed_status_applies_result_and_sets_completed_at(self):
        est = _FakeEstimation()
        db = AsyncMock()

        result = await apply_callback(
            db, est, status="completed", result=_FULL_AI_RESPONSE, error=None
        )

        assert result.status == "completed"
        assert result.estimation_markdown == _FULL_AI_RESPONSE["estimation"]
        assert result.completed_at is not None
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(est)

    async def test_failed_status_stores_error_detail(self):
        est = _FakeEstimation()
        db = AsyncMock()

        await apply_callback(db, est, status="failed", result=None, error="LLM timeout")

        assert est.status == "failed"
        assert est.error_detail == "LLM timeout"
        assert est.completed_at is None

    async def test_failed_status_does_not_apply_result(self):
        est = _FakeEstimation()
        db = AsyncMock()

        await apply_callback(
            db, est, status="failed", result=_FULL_AI_RESPONSE, error="error"
        )

        assert est.estimation_markdown is None

    async def test_commit_is_always_called(self):
        est = _FakeEstimation()
        db = AsyncMock()

        await apply_callback(db, est, status="completed", result=_FULL_AI_RESPONSE, error=None)
        db.commit.assert_awaited()

        db.reset_mock()
        await apply_callback(db, est, status="failed", result=None, error="err")
        db.commit.assert_awaited()

    async def test_completed_status_persists_prompt_version_from_callback_result(self):
        est = _FakeEstimation()
        est.prompt_version = "v1"
        db = AsyncMock()
        callback_result = {**_FULL_AI_RESPONSE, "prompt_version": "v2"}

        await apply_callback(db, est, status="completed", result=callback_result, error=None)

        assert est.prompt_version == "v2"
