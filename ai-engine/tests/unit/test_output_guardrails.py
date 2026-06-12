"""Unit tests for app/guardrails/ouput.py — enforce_scope_response filter.

Policy under test:
  - Results with confidence_pct >= LOW_CONFIDENCE_THRESHOLD pass through unchanged.
  - Results below the threshold whose summary does NOT start with OUT_OF_SCOPE_PREFIX
    are rewritten: summary prefixed, phases replaced, costs zeroed.
  - Results whose summary ALREADY starts with OUT_OF_SCOPE_PREFIX pass through
    unchanged (no double-wrapping).
"""
from __future__ import annotations

import pytest

from app.foundation.guardrails.ouput import enforce_scope_response
from app.domain.schemas.estimation import (
    LOW_CONFIDENCE_THRESHOLD,
    OUT_OF_SCOPE_PREFIX,
    EstimationResult,
    Phase,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phase(cost: int = 5_000) -> Phase:
    return Phase(name="Backend API", duration_weeks=2, cost_eur=cost, confidence_pct=80)


def _result(
    confidence_pct: int = 80,
    summary: str = "Web app project",
    cost: int = 5_000,
) -> EstimationResult:
    """Create a valid EstimationResult (phase costs sum == total_cost_eur)."""
    return EstimationResult(
        summary=summary,
        confidence_pct=confidence_pct,
        phases=[_phase(cost)],
        total_duration_weeks=2,
        total_cost_eur=cost,
    )


# ---------------------------------------------------------------------------
# Pass-through cases (no rewrite)
# ---------------------------------------------------------------------------

class TestPassThrough:
    def test_high_confidence_returns_same_object(self):
        result = _result(confidence_pct=80)
        assert enforce_scope_response(result) is result

    def test_exactly_at_threshold_returns_same_object(self):
        # boundary: >= LOW_CONFIDENCE_THRESHOLD must NOT be rewritten
        result = _result(confidence_pct=LOW_CONFIDENCE_THRESHOLD)
        assert enforce_scope_response(result) is result

    def test_already_marked_low_confidence_passes_through(self):
        """Low confidence but summary already has the prefix — must not double-wrap."""
        summary = f"{OUT_OF_SCOPE_PREFIX} already marked"
        result = _result(confidence_pct=5, summary=summary)
        out = enforce_scope_response(result)
        assert out is result

    def test_already_marked_summary_not_double_prefixed(self):
        summary = f"{OUT_OF_SCOPE_PREFIX} already marked"
        result = _result(confidence_pct=5, summary=summary)
        out = enforce_scope_response(result)
        assert out.summary.count(OUT_OF_SCOPE_PREFIX) == 1


# ---------------------------------------------------------------------------
# Rewrite cases (confidence below threshold, summary not yet marked)
# ---------------------------------------------------------------------------

class TestRewrite:
    def test_below_threshold_returns_new_object(self):
        result = _result(confidence_pct=LOW_CONFIDENCE_THRESHOLD - 1)
        assert enforce_scope_response(result) is not result

    def test_zero_confidence_is_rewritten(self):
        result = _result(confidence_pct=0)
        out = enforce_scope_response(result)
        assert out is not result

    def test_rewritten_summary_starts_with_scope_prefix(self):
        result = _result(confidence_pct=10)
        out = enforce_scope_response(result)
        assert out.summary.startswith(OUT_OF_SCOPE_PREFIX)

    def test_rewritten_summary_includes_original_rationale(self):
        original = "Not enough information about integrations and team"
        result = _result(confidence_pct=10, summary=original)
        out = enforce_scope_response(result)
        assert original in out.summary

    def test_rewritten_total_cost_eur_is_zero(self):
        result = _result(confidence_pct=10, cost=50_000)
        out = enforce_scope_response(result)
        assert out.total_cost_eur == 0

    def test_rewritten_total_duration_is_one_week(self):
        result = _result(confidence_pct=10)
        out = enforce_scope_response(result)
        assert out.total_duration_weeks == 1

    def test_rewritten_has_single_placeholder_phase(self):
        result = _result(confidence_pct=10)
        out = enforce_scope_response(result)
        assert len(out.phases) == 1

    def test_rewritten_placeholder_phase_name(self):
        result = _result(confidence_pct=10)
        out = enforce_scope_response(result)
        assert out.phases[0].name == "Not estimated"

    def test_rewritten_placeholder_phase_cost_is_zero(self):
        result = _result(confidence_pct=10)
        out = enforce_scope_response(result)
        assert out.phases[0].cost_eur == 0

    def test_original_confidence_pct_preserved(self):
        result = _result(confidence_pct=15)
        out = enforce_scope_response(result)
        assert out.confidence_pct == 15

    def test_rewritten_result_is_valid_estimation_result(self):
        """enforce_scope_response must return a well-formed EstimationResult
        (i.e. phase cost sum == total_cost_eur)."""
        result = _result(confidence_pct=5)
        out = enforce_scope_response(result)
        assert isinstance(out, EstimationResult)
        assert sum(p.cost_eur for p in out.phases) == out.total_cost_eur

    def test_summary_truncated_to_1200_chars(self):
        long_summary = "x" * 1500
        result = _result(confidence_pct=5, summary=long_summary)
        out = enforce_scope_response(result)
        assert len(out.summary) <= 1200

