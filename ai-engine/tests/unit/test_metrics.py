"""Tests for deterministic evaluation metrics."""

import pytest
from dataclasses import dataclass
from typing import Any, Optional

from tests.evals.deterministic_metrics import (
    LatencyBudgetMetric,
    CostBudgetMetric,
    MemoryDriftMetric,
    MetricResult,
)


# Mock objects for testing
@dataclass
class MockObservation:
    """Mock TurnObservedEvent for testing."""

    latency_ms: float = 1000.0
    cost_usd: float = 0.005


@dataclass
class MockMetadata:
    """Mock ProjectMetadata for testing."""

    project_name: Optional[str] = None
    assumed_team_size: Optional[int] = None
    mentioned_technologies: list[str] = None
    agreed_scope: Optional[str] = None

    def __post_init__(self):
        if self.mentioned_technologies is None:
            self.mentioned_technologies = []


@dataclass
class MockSessionSnapshot:
    """Mock session snapshot with summary, anchors, and metadata."""

    summary: str = ""
    anchors: list[dict[str, str]] = None
    metadata: MockMetadata = None

    def __post_init__(self):
        if self.anchors is None:
            self.anchors = []
        if self.metadata is None:
            self.metadata = MockMetadata()


class TestLatencyBudgetMetric:
    """Test LatencyBudgetMetric."""

    def test_within_budget(self):
        """Test observation with latency within budget."""
        metric = LatencyBudgetMetric(budget_ms=5000)
        obs = MockObservation(latency_ms=2500.0)

        result = metric.evaluate(obs)

        assert result.name == "latency_budget"
        assert result.score == 1.0
        assert result.passed is True
        assert "within" in result.details.lower()

    def test_exceeds_budget(self):
        """Test observation with latency exceeding budget."""
        metric = LatencyBudgetMetric(budget_ms=1000)
        obs = MockObservation(latency_ms=5000.0)

        result = metric.evaluate(obs)

        assert result.name == "latency_budget"
        assert result.score == 0.0
        assert result.passed is False
        assert "exceeded" in result.details.lower()

    def test_at_budget_boundary(self):
        """Test observation with latency exactly at budget."""
        metric = LatencyBudgetMetric(budget_ms=1000)
        obs = MockObservation(latency_ms=1000.0)

        result = metric.evaluate(obs)

        assert result.score == 1.0
        assert result.passed is True

    def test_missing_latency_field(self):
        """Test observation without latency_ms field."""
        metric = LatencyBudgetMetric(budget_ms=5000)
        obs = object()  # No latency_ms attribute

        result = metric.evaluate(obs)

        assert result.score == 0.0
        assert result.passed is False

    def test_negative_budget_raises(self):
        """Test that negative budget raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            LatencyBudgetMetric(budget_ms=-100)


class TestCostBudgetMetric:
    """Test CostBudgetMetric."""

    def test_within_budget(self):
        """Test observation with cost within budget."""
        metric = CostBudgetMetric(budget_usd=0.01)
        obs = MockObservation(cost_usd=0.005)

        result = metric.evaluate(obs)

        assert result.name == "cost_budget"
        assert result.score == 1.0
        assert result.passed is True
        assert "within" in result.details.lower()

    def test_exceeds_budget(self):
        """Test observation with cost exceeding budget."""
        metric = CostBudgetMetric(budget_usd=0.001)
        obs = MockObservation(cost_usd=0.01)

        result = metric.evaluate(obs)

        assert result.name == "cost_budget"
        assert result.score == 0.0
        assert result.passed is False
        assert "exceeded" in result.details.lower()

    def test_zero_budget(self):
        """Test with zero budget (free tier)."""
        metric = CostBudgetMetric(budget_usd=0.0)
        obs_free = MockObservation(cost_usd=0.0)
        obs_paid = MockObservation(cost_usd=0.001)

        result_free = metric.evaluate(obs_free)
        result_paid = metric.evaluate(obs_paid)

        assert result_free.score == 1.0
        assert result_paid.score == 0.0

    def test_missing_cost_field(self):
        """Test observation without cost_usd field."""
        metric = CostBudgetMetric(budget_usd=0.01)
        obs = object()  # No cost_usd attribute

        result = metric.evaluate(obs)

        assert result.score == 0.0
        assert result.passed is False

    def test_negative_budget_raises(self):
        """Test that negative budget raises ValueError."""
        with pytest.raises(ValueError, match="must be non-negative"):
            CostBudgetMetric(budget_usd=-0.01)


class TestMemoryDriftMetric:
    """Test MemoryDriftMetric."""

    def test_fact_found_in_summary(self):
        """Test fact found in summary text."""
        metric = MemoryDriftMetric(fact="React", where=["summary"])
        snapshot = MockSessionSnapshot(summary="We decided to use React for the frontend.")

        result = metric.evaluate(snapshot)

        assert result.name == "memory_drift"
        assert result.score == 1.0
        assert result.passed is True
        assert "summary" in result.details.lower()

    def test_fact_not_found(self):
        """Test fact not found anywhere."""
        metric = MemoryDriftMetric(fact="Vue", where=["summary", "metadata"])
        snapshot = MockSessionSnapshot(
            summary="We use React",
            metadata=MockMetadata(mentioned_technologies=["React", "Node"]),
        )

        result = metric.evaluate(snapshot)

        assert result.score == 0.0
        assert result.passed is False

    def test_case_insensitive_search(self):
        """Test that search is case-insensitive."""
        metric = MemoryDriftMetric(fact="REACT", where=["summary"])
        snapshot = MockSessionSnapshot(summary="We use react for frontend")

        result = metric.evaluate(snapshot)

        assert result.score == 1.0
        assert result.passed is True

    def test_fact_in_technologies_list(self):
        """Test fact found in mentioned_technologies list."""
        metric = MemoryDriftMetric(fact="Flutter", where=["metadata"])
        snapshot = MockSessionSnapshot(
            metadata=MockMetadata(mentioned_technologies=["React", "Flutter", "Node"])
        )

        result = metric.evaluate(snapshot)

        assert result.score == 1.0
        assert result.passed is True

    def test_fact_in_project_name(self):
        """Test fact found in project_name."""
        metric = MemoryDriftMetric(fact="CRM", where=["metadata"])
        snapshot = MockSessionSnapshot(
            metadata=MockMetadata(project_name="Customer CRM Platform")
        )

        result = metric.evaluate(snapshot)

        assert result.score == 1.0
        assert result.passed is True

    def test_fact_in_anchors(self):
        """Test fact found in anchors list."""
        metric = MemoryDriftMetric(fact="Team", where=["anchors"])
        snapshot = MockSessionSnapshot(
            anchors=[
                {"anchor_type": "team", "key_information": "Team size is 5"},
                {"anchor_type": "budget", "key_information": "€50,000"},
            ]
        )

        result = metric.evaluate(snapshot)

        assert result.score == 1.0
        assert result.passed is True

    def test_multiple_locations(self):
        """Test fact found in multiple locations."""
        metric = MemoryDriftMetric(fact="Python", where=["summary", "anchors", "metadata"])
        snapshot = MockSessionSnapshot(
            summary="Use Python for backend",
            anchors=[{"key_information": "Python experience required"}],
            metadata=MockMetadata(mentioned_technologies=["Python", "Django"]),
        )

        result = metric.evaluate(snapshot)

        assert result.score == 1.0
        assert result.passed is True
        assert result.details.count("found in") >= 1

    def test_default_where_all_fields(self):
        """Test that default 'where' searches all fields."""
        metric = MemoryDriftMetric(fact="React")  # No 'where' specified
        snapshot = MockSessionSnapshot(summary="We use React")

        result = metric.evaluate(snapshot)

        assert result.score == 1.0
        assert result.passed is True

    def test_invalid_where_field_raises(self):
        """Test that invalid 'where' field raises ValueError."""
        with pytest.raises(ValueError, match="Invalid where fields"):
            MemoryDriftMetric(fact="React", where=["invalid_field"])

    def test_empty_fact_raises(self):
        """Test that empty fact raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty string"):
            MemoryDriftMetric(fact="")

    def test_non_string_fact_raises(self):
        """Test that non-string fact raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty string"):
            MemoryDriftMetric(fact=123)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
