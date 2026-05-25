"""Deterministic metrics for stress test evaluation.

This module provides simple, deterministic metrics that measure:
- Latency against budget constraints
- Cost against budget constraints
- Memory drift of facts across multi-turn conversations

All metrics follow the MetricResult pattern: (name, score, passed, details).
No embeddings or LLM-as-judge; only exact string matching (case-insensitive).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MetricResult:
    """Standard result container for all metrics.

    Attributes:
        name: Metric identifier (e.g., "latency_budget")
        score: Normalized score (0.0 to 1.0, where 1.0 is ideal)
        passed: Boolean pass/fail based on threshold
        details: Free-text explanation of result
    """

    name: str
    score: float
    passed: bool
    details: str


class LatencyBudgetMetric:
    """Evaluate if latency stays within budget.

    Score: 1.0 if latency_ms <= budget_ms; 0.0 otherwise.

    Example:
        metric = LatencyBudgetMetric(budget_ms=5000)
        result = metric.evaluate(observation)
        # result.score = 1.0 if observation.latency_ms <= 5000 else 0.0
    """

    def __init__(self, budget_ms: int):
        """Initialize LatencyBudgetMetric.

        Args:
            budget_ms: Maximum acceptable latency in milliseconds.
        """
        if budget_ms <= 0:
            raise ValueError(f"budget_ms must be positive, got {budget_ms}")
        self.budget_ms = budget_ms

    def evaluate(self, observation: Any) -> MetricResult:
        """Evaluate latency against budget.

        Args:
            observation: Object with latency_ms attribute (e.g., TurnObservedEvent).

        Returns:
            MetricResult with score (1.0 if within budget, 0.0 if exceeded).
        """
        latency_ms = getattr(observation, "latency_ms", None)

        if latency_ms is None:
            return MetricResult(
                name="latency_budget",
                score=0.0,
                passed=False,
                details=f"latency_ms not found on observation",
            )

        within_budget = latency_ms <= self.budget_ms
        score = 1.0 if within_budget else 0.0

        details = (
            f"Latency {latency_ms:.1f}ms {'within' if within_budget else 'exceeded'} "
            f"budget {self.budget_ms}ms"
        )

        return MetricResult(
            name="latency_budget",
            score=score,
            passed=within_budget,
            details=details,
        )


class CostBudgetMetric:
    """Evaluate if cost stays within budget.

    Score: 1.0 if cost_usd <= budget_usd; 0.0 otherwise.

    Example:
        metric = CostBudgetMetric(budget_usd=0.10)
        result = metric.evaluate(observation)
        # result.score = 1.0 if observation.cost_usd <= 0.10 else 0.0
    """

    def __init__(self, budget_usd: float):
        """Initialize CostBudgetMetric.

        Args:
            budget_usd: Maximum acceptable cost in USD.
        """
        if budget_usd < 0:
            raise ValueError(f"budget_usd must be non-negative, got {budget_usd}")
        self.budget_usd = budget_usd

    def evaluate(self, observation: Any) -> MetricResult:
        """Evaluate cost against budget.

        Args:
            observation: Object with cost_usd attribute (e.g., TurnObservedEvent).

        Returns:
            MetricResult with score (1.0 if within budget, 0.0 if exceeded).
        """
        cost_usd = getattr(observation, "cost_usd", None)

        if cost_usd is None:
            return MetricResult(
                name="cost_budget",
                score=0.0,
                passed=False,
                details=f"cost_usd not found on observation",
            )

        within_budget = cost_usd <= self.budget_usd
        score = 1.0 if within_budget else 0.0

        details = (
            f"Cost ${cost_usd:.6f} {'within' if within_budget else 'exceeded'} "
            f"budget ${self.budget_usd:.6f}"
        )

        return MetricResult(
            name="cost_budget",
            score=score,
            passed=within_budget,
            details=details,
        )


class MemoryDriftMetric:
    """Evaluate if a fact declared at turn k appears in later turns.

    Score: 1.0 if fact found (case-insensitive exact match); 0.0 if not found.

    Searches across:
    - summary: Conversation summary text
    - anchors: Extracted key information anchors
    - metadata: ProjectMetadata fields (project_name, mentioned_technologies, etc.)

    Example:
        metric = MemoryDriftMetric(fact="React", where=["summary", "anchors"])
        result = metric.evaluate(session_snapshot)
        # result.score = 1.0 if "react" appears in summary or anchors, else 0.0
    """

    def __init__(
        self,
        fact: str,
        where: Optional[list[str]] = None,
    ):
        """Initialize MemoryDriftMetric.

        Args:
            fact: The fact string to search for (case-insensitive).
            where: List of field names to search in:
                - "summary": Conversation summary text
                - "anchors": Extracted key information anchors
                - "metadata": ProjectMetadata fields
                Defaults to ["summary", "anchors", "metadata"].
        """
        if not fact or not isinstance(fact, str):
            raise ValueError(f"fact must be a non-empty string, got {fact!r}")

        self.fact = fact.lower().strip()
        self.where = where or ["summary", "anchors", "metadata"]

        # Validate where values
        valid_fields = {"summary", "anchors", "metadata"}
        invalid = set(self.where) - valid_fields
        if invalid:
            raise ValueError(
                f"Invalid where fields: {invalid}. "
                f"Must be subset of {valid_fields}"
            )

    def evaluate(self, session_snapshot: Any) -> MetricResult:
        """Evaluate if fact is retained in session snapshot.

        Args:
            session_snapshot: Object containing turns, summary, anchors,
                and/or metadata fields to search.

        Returns:
            MetricResult with score (1.0 if found, 0.0 if not).
        """
        found_in = []

        # Search in summary (if present)
        if "summary" in self.where:
            summary = getattr(session_snapshot, "summary", None)
            if summary and self._fact_in_text(summary):
                found_in.append("summary")

        # Search in anchors (if present)
        if "anchors" in self.where:
            anchors = getattr(session_snapshot, "anchors", None)
            if anchors and self._fact_in_anchors(anchors):
                found_in.append("anchors")

        # Search in metadata (if present)
        if "metadata" in self.where:
            metadata = getattr(session_snapshot, "metadata", None)
            if metadata and self._fact_in_metadata(metadata):
                found_in.append("metadata")

        found = len(found_in) > 0
        score = 1.0 if found else 0.0

        if found:
            details = f"Fact '{self.fact}' found in: {', '.join(found_in)}"
        else:
            details = f"Fact '{self.fact}' not found in {self.where}"

        return MetricResult(
            name="memory_drift",
            score=score,
            passed=found,
            details=details,
        )

    def _fact_in_text(self, text: str) -> bool:
        """Check if fact appears as substring in text (case-insensitive)."""
        if not isinstance(text, str):
            return False
        return self.fact in text.lower()

    def _fact_in_anchors(self, anchors: Any) -> bool:
        """Check if fact appears in any anchor entry.

        Anchors can be:
        - List of dicts with 'key_information', 'anchor_type', etc.
        - List of strings
        - Any object with string representation
        """
        if not isinstance(anchors, (list, tuple)):
            # Try to convert to string and search
            return self._fact_in_text(str(anchors))

        for anchor in anchors:
            # If anchor is a dict, search all string values
            if isinstance(anchor, dict):
                for value in anchor.values():
                    if self._fact_in_text(str(value)):
                        return True
            else:
                # If anchor is a string or other type, convert and search
                if self._fact_in_text(str(anchor)):
                    return True

        return False

    def _fact_in_metadata(self, metadata: Any) -> bool:
        """Check if fact appears in ProjectMetadata fields.

        Searches: project_name, assumed_team_size, mentioned_technologies,
        agreed_scope (and any other string fields).
        """
        # Search key string fields
        for field_name in ["project_name", "agreed_scope"]:
            value = getattr(metadata, field_name, None)
            if self._fact_in_text(str(value)):
                return True

        # Search technologies list
        technologies = getattr(metadata, "mentioned_technologies", None)
        if technologies and isinstance(technologies, (list, tuple)):
            for tech in technologies:
                if self._fact_in_text(str(tech)):
                    return True

        # Search team_size as string
        team_size = getattr(metadata, "assumed_team_size", None)
        if team_size is not None and self._fact_in_text(str(team_size)):
            return True

        return False
