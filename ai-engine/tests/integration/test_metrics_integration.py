"""Integration tests for metrics with real project structures."""

import pytest
from app.schemas.observation import TurnObservedEvent, CacheHitKind
from app.services.sessions import ProjectMetadata
from evals.metrics import (
    LatencyBudgetMetric,
    CostBudgetMetric,
    MemoryDriftMetric,
)


class TestMetricsWithRealStructures:
    """Test metrics using actual project data structures."""

    def test_latency_budget_with_turn_observed_event(self):
        """Test LatencyBudgetMetric with real TurnObservedEvent."""
        event = TurnObservedEvent(
            turn_index=1,
            session_id="sess_test",
            enriched_transcript_chars=1000,
            attachments_total_chars=0,
            messages_in_window=2,
            anchors_count=1,
            summary_chars=200,
            tokens_in=500,
            tokens_out=250,
            cost_usd=0.005,
            latency_ms=2500.0,
            cache_hit_kind=CacheHitKind.NONE,
            last_resolved_tier="standard",
            model="gpt-4o-mini",
            response_id="resp_123",
        )

        metric = LatencyBudgetMetric(budget_ms=3000)
        result = metric.evaluate(event)

        assert result.passed is True
        assert result.score == 1.0
        assert "2500.0ms" in result.details

    def test_cost_budget_with_turn_observed_event(self):
        """Test CostBudgetMetric with real TurnObservedEvent."""
        event = TurnObservedEvent(
            turn_index=2,
            session_id="sess_test",
            enriched_transcript_chars=2000,
            attachments_total_chars=500,
            messages_in_window=3,
            anchors_count=2,
            summary_chars=400,
            tokens_in=1000,
            tokens_out=500,
            cost_usd=0.008,
            latency_ms=3500.0,
            cache_hit_kind=CacheHitKind.SEMANTIC,
            model="claude-3-haiku-20240307",
            response_id="resp_456",
        )

        metric = CostBudgetMetric(budget_usd=0.01)
        result = metric.evaluate(event)

        assert result.passed is True
        assert result.score == 1.0
        assert "$0.008000" in result.details

    def test_memory_drift_with_project_metadata(self):
        """Test MemoryDriftMetric with real ProjectMetadata."""
        metadata = ProjectMetadata(
            project_name="E-commerce Platform",
            assumed_team_size=5,
            mentioned_technologies=["React", "Node.js", "PostgreSQL", "Redis"],
            agreed_scope="Build a multi-vendor e-commerce platform with admin dashboard",
        )

        # Check technology is retained
        metric = MemoryDriftMetric(fact="React", where=["metadata"])
        result = metric.evaluate(
            type("SnapshotWithMetadata", (), {"metadata": metadata})()
        )

        assert result.passed is True
        assert result.score == 1.0
        assert "react" in result.details.lower()

    def test_memory_drift_case_insensitive_with_real_metadata(self):
        """Test case-insensitive search with real metadata."""
        metadata = ProjectMetadata(
            mentioned_technologies=["react", "node", "postgresql"],
        )

        metric = MemoryDriftMetric(fact="REACT", where=["metadata"])
        result = metric.evaluate(
            type("SnapshotWithMetadata", (), {"metadata": metadata})()
        )

        assert result.passed is True

    def test_multiple_metrics_on_same_observation(self):
        """Test multiple metrics on the same observation."""
        event = TurnObservedEvent(
            turn_index=1,
            session_id="sess_multi",
            enriched_transcript_chars=1500,
            attachments_total_chars=0,
            messages_in_window=2,
            anchors_count=1,
            summary_chars=300,
            tokens_in=750,
            tokens_out=300,
            cost_usd=0.006,
            latency_ms=2000.0,
            cache_hit_kind=CacheHitKind.EXACT,
            model="gpt-4o-mini",
            response_id="resp_789",
        )

        latency_metric = LatencyBudgetMetric(budget_ms=3000)
        cost_metric = CostBudgetMetric(budget_usd=0.01)

        latency_result = latency_metric.evaluate(event)
        cost_result = cost_metric.evaluate(event)

        assert latency_result.passed is True
        assert cost_result.passed is True
        assert latency_result.score == 1.0
        assert cost_result.score == 1.0

    def test_exceeding_latency_budget(self):
        """Test latency metric when budget is exceeded."""
        event = TurnObservedEvent(
            turn_index=3,
            session_id="sess_slow",
            enriched_transcript_chars=5000,
            attachments_total_chars=2000,
            messages_in_window=5,
            anchors_count=3,
            summary_chars=800,
            tokens_in=2000,
            tokens_out=1000,
            cost_usd=0.02,
            latency_ms=8500.0,  # Exceeds budget
            cache_hit_kind=CacheHitKind.NONE,
            model="claude-3-opus",
            response_id="resp_slow",
        )

        metric = LatencyBudgetMetric(budget_ms=5000)
        result = metric.evaluate(event)

        assert result.passed is False
        assert result.score == 0.0
        assert "exceeded" in result.details.lower()

    def test_exceeding_cost_budget(self):
        """Test cost metric when budget is exceeded."""
        event = TurnObservedEvent(
            turn_index=1,
            session_id="sess_expensive",
            enriched_transcript_chars=10000,
            attachments_total_chars=5000,
            messages_in_window=10,
            anchors_count=5,
            summary_chars=1500,
            tokens_in=5000,
            tokens_out=2000,
            cost_usd=0.15,  # Exceeds budget
            latency_ms=5000.0,
            cache_hit_kind=CacheHitKind.NONE,
            model="gpt-4o",
            response_id="resp_expensive",
        )

        metric = CostBudgetMetric(budget_usd=0.10)
        result = metric.evaluate(event)

        assert result.passed is False
        assert result.score == 0.0
        assert "exceeded" in result.details.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
