"""Integration tests for synthetic multi-turn scenario stress tests.

Tests memory retention, metadata consistency, and cost curves across scenarios
designed to expose system behavior under growth, pivots, and contradictions.

Markers:
  - slow: Multiple turns per scenario (cost in LLM calls)
  - llm_live: Makes real API calls (requires ANTHROPIC_API_KEY, OPENAI_API_KEY)
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.llm_live]


# ---------------------------------------------------------------------------
# Fixtures — isolated evaluator for each test
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_session_store():
    """Clear the in-memory store before/after to prevent state leakage."""
    from app.generation.conversation import sessions as sessions_module
    sessions_module.store._sessions.clear()
    yield
    sessions_module.store._sessions.clear()


@pytest.fixture
def scenario_evaluator(reset_session_store):
    """Create a fresh evaluator for each test."""
    from tests.stress.scenarios import MultiTurnScenarioEvaluator
    return MultiTurnScenarioEvaluator(use_http_client=True)


# ---------------------------------------------------------------------------
# Test: Project Growth Scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_growth_scenario(scenario_evaluator):
    """Growth scenario: MVP → auth → multi-tenant → audit → export.

    Expected behavior:
      - Cost increases monotonically
      - project_name 'TaskMaster' survives all 5 turns
      - mentioned_technologies accumulate (never remove)
    """
    from tests.stress.scenarios import ProjectGrowthScenario, ScenarioConfig

    config = ScenarioConfig(scenario=ProjectGrowthScenario(), turn_counts=[1, 3, 6, 10, 20])
    result = await scenario_evaluator.run_scenario(config)

    # Assert no errors
    assert result.error is None, f"Scenario failed: {result.error}"

    # Assert at least some turns ran
    assert len(result.turns) > 0, "No turns executed"

    # Assert cost curve is monotonic
    cost_curve = result.cost_curve
    for i in range(1, len(cost_curve)):
        assert cost_curve[i] >= cost_curve[i - 1], (
            f"Cost curve not monotonic: {cost_curve}"
        )

    # Assert project name survives
    assert result.final_project_name is not None, "Project name not preserved"
    assert "TaskMaster" in result.final_project_name or "taskmast" in result.final_project_name.lower(), (
        f"Project name changed to: {result.final_project_name}"
    )

    # Assert technologies accumulate
    final_techs = [t.lower() for t in result.final_technologies]
    assert any("react" in t or "node" in t or "postgre" in t for t in final_techs), (
        f"Initial technologies lost: {result.final_technologies}"
    )

    # Memory drift should be low (facts are being remembered)
    assert result.avg_memory_drift < 0.3, (
        f"Memory drift too high: {result.avg_memory_drift:.2%}"
    )


# ---------------------------------------------------------------------------
# Test: Project Pivot Scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_pivot_scenario(scenario_evaluator):
    """Pivot scenario: React → Flutter (turn 5).

    Expected behavior:
      - Technology pivot is recognized
      - Flutter becomes primary technology by turn 20
      - Cleanest behavior: React is superseded (not accumulated)
    """
    from tests.stress.scenarios import ProjectPivotScenario, ScenarioConfig

    config = ScenarioConfig(scenario=ProjectPivotScenario(), turn_counts=[1, 3, 5, 10, 20])
    result = await scenario_evaluator.run_scenario(config)

    assert result.error is None, f"Scenario failed: {result.error}"
    assert len(result.turns) > 0

    # Check that Flutter is mentioned in final technologies
    final_techs = [t.lower() for t in result.final_technologies]
    assert any("flutter" in t for t in final_techs), (
        f"Flutter not in final technologies: {result.final_technologies}"
    )

    # Project name should survive the pivot
    assert result.final_project_name is not None
    assert "SalesFlow" in result.final_project_name or "salesflow" in result.final_project_name.lower(), (
        f"Project name changed: {result.final_project_name}"
    )

    # Memory drift should be moderate (pivot is a change, but expected)
    assert result.avg_memory_drift < 0.4, (
        f"Memory drift too high for pivot: {result.avg_memory_drift:.2%}"
    )


# ---------------------------------------------------------------------------
# Test: Project Contradiction Scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_contradiction_scenario(scenario_evaluator):
    """Contradiction scenario: Budget €30k → €80k (turn 8).

    Expected behavior:
      - Both budgets are encountered
      - Final budget should be €80k (later value wins, or explicitly anchored)
      - Contradiction is documented (memory drift spike at turn 8)
    """
    from tests.stress.scenarios import ProjectContradictionScenario, ScenarioConfig

    config = ScenarioConfig(scenario=ProjectContradictionScenario(), turn_counts=[1, 3, 8, 20])
    result = await scenario_evaluator.run_scenario(config)

    assert result.error is None, f"Scenario failed: {result.error}"
    assert len(result.turns) > 0

    # Project name should survive contradiction
    assert result.final_project_name is not None
    assert "LogHub" in result.final_project_name or "loghub" in result.final_project_name.lower(), (
        f"Project name changed: {result.final_project_name}"
    )

    # Check individual turn memory drift — expect a spike at turn 8 (contradiction)
    if len(result.turns) >= 3:
        turn_8_drift = result.turns[2].memory_drift if len(result.turns) > 2 else None
        if turn_8_drift is not None:
            # Contradiction turn should have higher drift (facts conflict)
            # But subsequent turns may recover as the new value is established
            assert turn_8_drift <= 0.8, (
                f"Extreme drift at contradiction turn: {turn_8_drift:.2%}"
            )


# ---------------------------------------------------------------------------
# Test: Cost Estimation Across Scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_costs_reasonable(scenario_evaluator):
    """Verify that total costs across all scenarios are in expected range.

    Each turn costs roughly $0.0001-0.001 depending on model.
    5 turns × 3 scenarios = 15 turns ≈ $0.005-0.015 total.
    """
    from tests.stress.scenarios import (
        ProjectGrowthScenario,
        ProjectPivotScenario,
        ProjectContradictionScenario,
        ScenarioConfig,
    )

    total_cost = Decimal(0)

    for scenario_class in [ProjectGrowthScenario, ProjectPivotScenario, ProjectContradictionScenario]:
        config = ScenarioConfig(scenario=scenario_class(), turn_counts=[1, 3, 6, 10, 20])
        result = await scenario_evaluator.run_scenario(config)
        assert result.error is None
        total_cost += result.total_cost_usd

    # Total cost should be reasonable (< $1 for all 15 turns)
    assert total_cost < Decimal(1), (
        f"Total cost unexpectedly high: ${float(total_cost):.4f}"
    )

    # But not zero (should have made actual calls)
    assert total_cost > Decimal(0.0001), (
        f"Total cost too low (may not have called LLM): ${float(total_cost):.4f}"
    )


# ---------------------------------------------------------------------------
# Test: Memory Drift Metric (Fact-Tracker Integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fact_tracker_memory_drift_metric(scenario_evaluator):
    """Verify FactTracker correctly measures violations.

    - Create a scenario
    - Run turns
    - Check that memory_drift_ratio matches (violated / total)
    """
    from tests.stress.scenarios import ProjectGrowthScenario, ScenarioConfig

    config = ScenarioConfig(scenario=ProjectGrowthScenario(), turn_counts=[1, 3, 6])
    result = await scenario_evaluator.run_scenario(config)

    assert result.error is None

    # For each turn, verify memory_drift ratio calculation
    for turn in result.turns:
        total_facts = len(turn.satisfied_facts) + len(turn.violated_facts)
        if total_facts > 0:
            expected_drift = len(turn.violated_facts) / total_facts
            assert turn.memory_drift == pytest.approx(expected_drift), (
                f"Memory drift mismatch at turn {turn.turn_number}: "
                f"expected {expected_drift}, got {turn.memory_drift}"
            )
        else:
            assert turn.memory_drift == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Helper Tests
# ---------------------------------------------------------------------------


def test_fact_tracker_match_string():
    """Test FactTracker._match for string containment."""
    from tests.stress.scenarios import FactTracker

    assert FactTracker._match("react frontend", "react") is True
    assert FactTracker._match("React Frontend", "react") is True
    assert FactTracker._match("flutter app", "react") is False


def test_fact_tracker_match_list():
    """Test FactTracker._match for list containment."""
    from tests.stress.scenarios import FactTracker

    assert FactTracker._match(["React", "Node.js"], ["React"]) is True
    assert FactTracker._match(["React", "Node.js"], ["React", "Node.js"]) is True
    assert FactTracker._match(["React"], ["React", "Node.js"]) is False
    assert FactTracker._match([], ["React"]) is False


def test_scenario_result_cost_curve():
    """Test ScenarioResult cost curve calculation."""
    from decimal import Decimal

    from tests.stress.scenarios import ScenarioResult, TurnResult, ScenarioType

    result = ScenarioResult(scenario_id="test", profile=ScenarioType.GROWTH)

    # Add turns with costs
    for i, cost in enumerate([Decimal("0.001"), Decimal("0.002"), Decimal("0.003")], 1):
        turn = TurnResult(
            turn_number=i,
            transcript=f"Turn {i}",
            response="Response",
            cost_usd=cost,
            input_tokens=100,
            output_tokens=50,
            latency_ms=500.0,
        )
        result.add_turn(turn)

    # Verify cumulative curve
    curve = result.cost_curve
    assert len(curve) == 3
    assert curve[0] == Decimal("0.001")
    assert curve[1] == Decimal("0.003")
    assert curve[2] == Decimal("0.006")
