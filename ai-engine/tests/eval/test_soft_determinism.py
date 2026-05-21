"""Family 2 — Soft determinism tests.

These tests verify *statistical properties* of the system, not a specific response.
They run the estimation pipeline N times on the same input and assert that the
distribution of results has the expected shape.

Two properties are checked:
  1. Consistency: the coefficient of variation (CV) of total hours across N runs
     must stay below a threshold (25%).
  2. Plausible range: total hours must fall within 50% slack of the expected range
     defined in the golden dataset.

Run flags
---------
Both marks must be active for these tests to execute:

    pytest -m "slow and llm_live" tests/eval/

During normal development, skip with:

    pytest -m "not slow"

Cost profile: 3 runs × 3 goldens = 9 real LLM calls per execution.
"""
from __future__ import annotations

import statistics

import pytest

from tests.eval.golden_dataset import GOLDEN_CASES, extract_total_hours, run_estimate

pytestmark = [pytest.mark.slow, pytest.mark.llm_live]

# Only run consistency tests on the first 3 goldens to control cost.
# The ambiguous and edge-case goldens intentionally have wide variance.
_CONSISTENCY_GOLDENS = GOLDEN_CASES[:3]
_N_RUNS = 3
_CV_THRESHOLD = 0.25  # 25% relative variability is the acceptance limit


# ---------------------------------------------------------------------------
# Consistency across runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "golden",
    _CONSISTENCY_GOLDENS,
    ids=[g["id"] for g in _CONSISTENCY_GOLDENS],
)
async def test_estimate_consistency(golden):
    """Same transcript → CV of total hours < 0.25 across N runs.

    If fewer than 2 runs return parseable hours the test fails with a clear
    message pointing to the hard-determinism suite (test_output_validator).
    """
    responses = [await run_estimate(golden["transcript"]) for _ in range(_N_RUNS)]

    hours = [extract_total_hours(r) for r in responses]
    extracted = [h for h in hours if h is not None]

    assert len(extracted) >= 2, (
        f"[{golden['id']}] Only {len(extracted)}/{_N_RUNS} runs returned parseable hours: "
        f"{hours}. This is a hard structure failure — check tests/unit/test_output_validator.py."
    )

    mean = statistics.mean(extracted)
    cv = statistics.stdev(extracted) / mean

    assert cv < _CV_THRESHOLD, (
        f"[{golden['id']}] Inconsistent estimates across runs: "
        f"CV={cv:.2f} (threshold={_CV_THRESHOLD}), "
        f"hours={extracted}, mean={mean:.0f}h"
    )


# ---------------------------------------------------------------------------
# Plausible range (single run — cheaper than N runs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "golden",
    _CONSISTENCY_GOLDENS,
    ids=[g["id"] for g in _CONSISTENCY_GOLDENS],
)
async def test_estimate_within_plausible_range(golden):
    """Total hours falls within 50% slack of the expected range.

    The 50% slack is intentionally generous for a first pass — it detects
    catastrophic failures (landing page estimated at 800h) without penalising
    legitimate model variance. Tighten as the system matures.
    """
    response = await run_estimate(golden["transcript"])

    hours = extract_total_hours(response)

    if hours is None:
        pytest.skip(
            f"[{golden['id']}] No parseable hours in response. "
            "Hard structure tests handle this failure."
        )

    low_bound = golden["expected_hours_min"] * 0.5
    high_bound = golden["expected_hours_max"] * 1.5

    assert low_bound <= hours <= high_bound, (
        f"[{golden['id']}] Estimated {hours}h is outside plausible range "
        f"[{low_bound:.0f}–{high_bound:.0f}h] "
        f"(50% slack around [{golden['expected_hours_min']}–{golden['expected_hours_max']}h])"
    )
