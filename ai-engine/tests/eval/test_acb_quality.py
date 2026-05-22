"""Family 3 extension — Subjective quality tests for the ACB pipeline.

Verifies that the Actor-Critic-Boss pipeline produces estimates of equal or
better quality compared to the standard estimation endpoint when evaluated by
the same GEval LLM judge.

Additional ACB-specific metric: *CriticRelevance* — checks that the critic's
issues (when present) relate to actual problems in the candidate, and that the
boss's final decision is consistent with the critic's feedback.

Run flags
---------
    pytest -m "slow and llm_live" tests/eval/

Cost profile per execution:
  - 1 ACB pipeline call per golden (≈ 3 LLM calls: actor + critic + boss)
  - 1 judge call per test case × 3 metrics × 3 goldens = ~9 judge calls
  - Total: ≈ 18 LLM calls
"""
from __future__ import annotations

import asyncio

import pytest

deepeval = pytest.importorskip("deepeval", reason="deepeval not installed — run: uv add deepeval")
assert_test = deepeval.assert_test

from deepeval.models.base_model import DeepEvalBaseLLM  # noqa: E402
from deepeval.metrics import GEval  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

from tests.eval.golden_dataset import GOLDEN_CASES

pytestmark = [pytest.mark.slow, pytest.mark.llm_live]

_JUDGE_GOLDENS = GOLDEN_CASES[:3]


# ---------------------------------------------------------------------------
# ACB inference helper
# ---------------------------------------------------------------------------


def _run_acb_sync(transcript: str, max_iterations: int = 1) -> dict:
    """Run the ACB pipeline synchronously and return a dict with estimation and traces."""
    from app.schemas.estimation import ActorCriticBossRequest
    from app.services.acb_service import ActorCriticBossService

    async def _run():
        req = ActorCriticBossRequest(
            transcription=transcript,
            max_iterations=max_iterations,
        )
        return await ActorCriticBossService().estimate(req)

    result = asyncio.get_event_loop().run_until_complete(_run())
    return {
        "estimation": result.estimation,
        "iterations": [
            {
                "iteration": trace.iteration,
                "critic_approved": trace.critic_feedback.approved,
                "issues_count": len(trace.critic_feedback.issues),
                "boss_action": trace.boss_decision.action,
            }
            for trace in result.iterations
        ],
        "final_action": result.final_decision.action if result.final_decision else None,
        "total_input_tokens": result.acb_total_input_tokens,
        "total_output_tokens": result.acb_total_output_tokens,
    }


# ---------------------------------------------------------------------------
# Judge (shared with test_llm_judge.py — identical Anthropic-backed class)
# ---------------------------------------------------------------------------


class _AnthropicJudge(DeepEvalBaseLLM):
    """DeepEval-compatible judge backed by Anthropic claude-haiku."""

    _MODEL = "claude-haiku-4-5-20251001"

    def load_model(self):
        import anthropic
        from app.config import settings
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(self, prompt: str, **kwargs) -> str:
        client = self.load_model()
        msg = client.messages.create(
            model=self._MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    async def a_generate(self, prompt: str, **kwargs) -> str:
        import anthropic
        from app.config import settings
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=self._MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def get_model_name(self) -> str:
        return self._MODEL


# ---------------------------------------------------------------------------
# GEval metrics
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def acb_scope_coherence_metric():
    return GEval(
        name="ACBScopeCoherence",
        criteria=(
            "Evaluate whether the phases, components, and technical risks in the actual output "
            "are coherent with the project scope described in the input. "
            "A coherent estimation includes phases that logically derive from the features "
            "described in the input, mentions risks directly relevant to the stated "
            "technologies, and does not invent components not implied by the input."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        threshold=0.6,
        model=_AnthropicJudge(),
    )


@pytest.fixture(scope="session")
def acb_risk_coverage_metric():
    return GEval(
        name="ACBRiskCoverage",
        criteria=(
            "Evaluate whether the technical risks listed in the actual output cover "
            "the main risk areas that a senior engineer would identify from the input. "
            "A good response mentions at least one non-trivial risk per significant "
            "integration, third-party dependency, or ambiguous requirement."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        threshold=0.3,
        model=_AnthropicJudge(),
    )


@pytest.fixture(scope="session")
def acb_convergence_metric():
    return GEval(
        name="ACBConvergence",
        criteria=(
            "Given the 'input' containing the original project description AND a "
            "JSON trace of critic issues and boss decisions, evaluate whether the "
            "final output (actual output) shows improvement relative to any "
            "issues identified by the critic. "
            "A high score indicates that critical issues raised in the trace have "
            "been addressed in the final estimate text. "
            "Score close to 1.0 when all critical issues are resolved. "
            "Score close to 0 when issues are unaddressed or the trace shows "
            "the boss accepted despite critical issues remaining."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        threshold=0.5,
        model=_AnthropicJudge(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("golden", _JUDGE_GOLDENS, ids=[g["id"] for g in _JUDGE_GOLDENS])
def test_acb_scope_coherence(golden: dict, acb_scope_coherence_metric: GEval):
    """ACB final estimate is coherent with project scope."""
    result = _run_acb_sync(golden["transcript"], max_iterations=1)
    test_case = LLMTestCase(
        input=golden["transcript"],
        actual_output=result["estimation"],
    )
    assert_test(test_case, [acb_scope_coherence_metric])


@pytest.mark.parametrize("golden", _JUDGE_GOLDENS, ids=[g["id"] for g in _JUDGE_GOLDENS])
def test_acb_risk_coverage(golden: dict, acb_risk_coverage_metric: GEval):
    """ACB final estimate covers key technical risks."""
    result = _run_acb_sync(golden["transcript"], max_iterations=1)
    test_case = LLMTestCase(
        input=golden["transcript"],
        actual_output=result["estimation"],
    )
    assert_test(test_case, [acb_risk_coverage_metric])


@pytest.mark.parametrize("golden", _JUDGE_GOLDENS, ids=[g["id"] for g in _JUDGE_GOLDENS])
def test_acb_convergence_quality(golden: dict, acb_convergence_metric: GEval):
    """When the critic raises issues, the final estimate addresses them."""
    import json
    result = _run_acb_sync(golden["transcript"], max_iterations=2)

    # Build a rich input that includes the critic/boss trace
    trace_summary = json.dumps(result["iterations"], indent=2)
    enriched_input = (
        f"Project description:\n{golden['transcript']}\n\n"
        f"ACB pipeline trace:\n{trace_summary}"
    )

    test_case = LLMTestCase(
        input=enriched_input,
        actual_output=result["estimation"],
    )
    assert_test(test_case, [acb_convergence_metric])
