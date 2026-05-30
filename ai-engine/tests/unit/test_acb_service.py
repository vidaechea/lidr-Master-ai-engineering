"""Unit tests for the Actor-Critic-Boss estimation service.

Verifies the control flow, guardrail integration, iteration budget cap,
boss action dispatch, and cost accumulation without making any real LLM calls.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.guardrails.input import InputGuardrailViolation
from app.schemas.estimation import (
    ActorCriticBossRequest,
    BossAction,
    BossDecision,
    CriticFeedback,
    CriticIssue,
    IssueCategory,
    IssueSeverity,
)
from app.schemas.llm import LLMObservableResponse, LLMUsage
from app.services.acb_service import ActorCriticBossService

VALID_TRANSCRIPTION = (
    "Build a SaaS platform with user authentication, a reporting dashboard, "
    "and billing integration via Stripe."
)

_REQUEST = ActorCriticBossRequest(transcription=VALID_TRANSCRIPTION, max_iterations=2)
_REQUEST_ZERO = ActorCriticBossRequest(transcription=VALID_TRANSCRIPTION, max_iterations=0)
_REQUEST_ONE = ActorCriticBossRequest(transcription=VALID_TRANSCRIPTION, max_iterations=1)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_actor_response(content: str = "## Estimate\nTotal: 100 h / 80 000 EUR", response_id: str = "actor-resp-001") -> LLMObservableResponse:
    return LLMObservableResponse(
        model="gpt-4o-mini",
        content=content,
        usage=LLMUsage(
            prompt_tokens=400,
            completion_tokens=200,
            total_tokens=600,
        ),
        latency_ms=150.0,
        cost_usd=Decimal("0.001"),
        response_id=response_id,
    )


def _make_completion(in_tok: int = 100, out_tok: int = 50) -> LLMObservableResponse:
    return LLMObservableResponse(
        model="gpt-4o-mini",
        content="{}",
        usage=LLMUsage(
            prompt_tokens=in_tok,
            completion_tokens=out_tok,
            total_tokens=in_tok + out_tok,
        ),
        latency_ms=100.0,
        cost_usd=Decimal("0.0005"),
        response_id="structured-resp-001",
    )


def _approved_critic() -> CriticFeedback:
    return CriticFeedback(
        issues=[],
        overall_assessment="Estimate is complete and internally consistent.",
        approved=True,
    )


def _major_critic() -> CriticFeedback:
    return CriticFeedback(
        issues=[
            CriticIssue(
                category=IssueCategory.ARITHMETIC_ERROR,
                severity=IssueSeverity.MAJOR,
                affected_field="total_cost_eur",
                description="Phase costs sum to 70 000 EUR but total_cost_eur states 80 000 EUR.",
            )
        ],
        overall_assessment="Arithmetic error found in total cost.",
        approved=False,
    )


def _minor_critic() -> CriticFeedback:
    return CriticFeedback(
        issues=[
            CriticIssue(
                category=IssueCategory.RISK_GAP,
                severity=IssueSeverity.MINOR,
                affected_field="technical_risks",
                description="Stripe SCA regulation risk not mentioned.",
            )
        ],
        overall_assessment="Minor risk gap; estimate is otherwise solid.",
        approved=False,
    )


def _accept_decision() -> BossDecision:
    return BossDecision(action=BossAction.ACCEPT, reasoning="Critic approved the estimate.")


def _iterate_decision() -> BossDecision:
    return BossDecision(
        action=BossAction.ITERATE,
        reasoning="Major arithmetic error; correctable in a single pass.",
        iteration_instructions=(
            "Fix total_cost_eur: sum all phase costs (they total 70 000 EUR) "
            "and update the declared total to match."
        ),
    )


def _synthesize_decision(text: str = "## Synthesized\nTotal: 70 000 EUR (corrected)") -> BossDecision:
    return BossDecision(
        action=BossAction.SYNTHESIZE,
        reasoning="Budget exhausted; synthesising best available result.",
        synthesized_estimate=text,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestActorCriticBossServiceHappyPath:
    async def test_single_pass_accept(self):
        """Critic approves → boss accepts → 1 iteration, candidate returned unchanged."""
        completion = _make_completion()
        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=_make_actor_response()),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_approved_critic(), completion),
                    (_accept_decision(), completion),
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST)

        assert result.estimation == "## Estimate\nTotal: 100 h / 80 000 EUR"
        assert len(result.iterations) == 1
        assert result.final_decision is not None
        assert result.final_decision.action == BossAction.ACCEPT

    async def test_minor_issues_accept(self):
        """Boss accepts even when critic finds only minor issues."""
        completion = _make_completion()
        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=_make_actor_response()),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_minor_critic(), completion),
                    (_accept_decision(), completion),
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST)

        assert result.final_decision.action == BossAction.ACCEPT
        assert len(result.iterations) == 1

    async def test_iterate_then_accept(self):
        """Boss iterates once on major issue, accepts on second pass."""
        completion = _make_completion()
        actor_calls = [
            _make_actor_response("## Draft v1"),
            _make_actor_response("## Revised v2 — corrected total"),
        ]
        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(side_effect=actor_calls),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_major_critic(), completion),    # critic it=0
                    (_iterate_decision(), completion), # boss it=0
                    (_approved_critic(), completion),  # critic it=1
                    (_accept_decision(), completion),  # boss it=1
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST)

        assert len(result.iterations) == 2
        assert result.estimation == "## Revised v2 — corrected total"
        assert result.final_decision.action == BossAction.ACCEPT

    async def test_synthesize_uses_boss_text(self):
        """Boss synthesise action returns synthesized_estimate as final text."""
        completion = _make_completion()
        synth_text = "## Synthesized final estimate"
        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=_make_actor_response()),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_major_critic(), completion),
                    (_synthesize_decision(synth_text), completion),
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST_ZERO)

        assert result.estimation == synth_text
        assert result.final_decision.action == BossAction.SYNTHESIZE


class TestActorCriticBossServiceBudget:
    async def test_budget_zero_runs_exactly_one_iteration(self):
        """max_iterations=0 → loop executes once, boss cannot iterate."""
        completion = _make_completion()
        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=_make_actor_response("## Single pass")),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_major_critic(), completion),
                    (_iterate_decision(), completion),  # boss says iterate but budget=0
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST_ZERO)

        # iterate at iteration==max_iterations(0) → budget_exhausted fallback
        assert result.estimation == "## Single pass"
        assert len(result.iterations) == 1

    async def test_budget_one_iterate_then_budget_exhausted(self):
        """max_iterations=1 → iterate once, then budget exhausted → fall back."""
        completion = _make_completion()
        actor_calls = [
            _make_actor_response("## Draft v1"),
            _make_actor_response("## Draft v2 still wrong"),
        ]
        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(side_effect=actor_calls),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_major_critic(), completion),    # critic it=0
                    (_iterate_decision(), completion), # boss it=0  → iterate, budget now at limit
                    (_major_critic(), completion),    # critic it=1
                    (_iterate_decision(), completion), # boss it=1  → iterate but budget exhausted
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST_ONE)

        assert len(result.iterations) == 2
        assert result.estimation == "## Draft v2 still wrong"


class TestActorCriticBossServiceGuardrails:
    async def test_violation_propagates_before_llm(self):
        violation = InputGuardrailViolation("Email detected.", reason="pii")
        with patch("app.services.acb_service.check_input", side_effect=violation):
            with pytest.raises(InputGuardrailViolation) as exc_info:
                await ActorCriticBossService().estimate(_REQUEST)
        assert exc_info.value.reason == "pii"

    async def test_check_input_called_exactly_once(self):
        """Guardrail must fire once regardless of max_iterations value."""
        mock_check = MagicMock()
        completion = _make_completion()
        with (
            patch("app.services.acb_service.check_input", mock_check),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=_make_actor_response()),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_approved_critic(), completion),
                    (_accept_decision(), completion),
                ]),
            ),
        ):
            await ActorCriticBossService().estimate(_REQUEST)

        mock_check.assert_called_once()

    async def test_llm_not_called_when_guardrail_raises(self):
        violation = InputGuardrailViolation("Injection.", reason="prompt_injection")
        mock_complete = AsyncMock()
        with (
            patch("app.services.acb_service.check_input", side_effect=violation),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete", mock_complete
            ),
        ):
            with pytest.raises(InputGuardrailViolation):
                await ActorCriticBossService().estimate(_REQUEST)

        mock_complete.assert_not_called()


class TestActorCriticBossServiceCosts:
    async def test_costs_accumulate_across_all_roles(self):
        """Total tokens = actor + critic + boss."""
        actor_resp = _make_actor_response()
        actor_resp.usage.prompt_tokens = 400
        actor_resp.usage.completion_tokens = 200
        critic_completion = _make_completion(in_tok=100, out_tok=50)
        boss_completion = _make_completion(in_tok=150, out_tok=75)

        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=actor_resp),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_approved_critic(), critic_completion),
                    (_accept_decision(), boss_completion),
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST)

        assert result.acb_total_input_tokens == 400 + 100 + 150
        assert result.acb_total_output_tokens == 200 + 50 + 75
        assert result.total_cost_usd > 0

    async def test_response_metadata_fields_populated(self):
        """response_id, model, prompt_version, tier are set correctly."""
        actor_resp = _make_actor_response(response_id="actor-id-xyz")
        completion = _make_completion()

        with (
            patch("app.services.acb_service.check_input"),
            patch("app.services.acb_service._get_moderation_client", return_value=None),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete",
                AsyncMock(return_value=actor_resp),
            ),
            patch(
                "app.services.litellm_service.LiteLLMRouterService.complete_structured",
                AsyncMock(side_effect=[
                    (_approved_critic(), completion),
                    (_accept_decision(), completion),
                ]),
            ),
        ):
            result = await ActorCriticBossService().estimate(_REQUEST, prompt_version="v2")

        assert result.response_id == "actor-id-xyz"
        assert result.prompt_version == "v2"
        assert result.model is not None
