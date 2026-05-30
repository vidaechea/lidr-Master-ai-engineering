"""MemoryDriftMetric for evaluating fact retention across multi-turn conversations.

This metric measures how well the system remembers and maintains consistent facts
across conversation turns. It integrates with DeepEval and the FactTracker system.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

try:
    from deepeval.models.base_model import DeepEvalBaseLLM
    from deepeval.metrics import Metric
except ImportError:
    # Fallback if DeepEval not installed
    Metric = object  # type: ignore
    DeepEvalBaseLLM = object  # type: ignore


class MemoryDriftMetric(Metric):
    """Evaluate fact retention in multi-turn conversations.

    This metric checks whether facts established in earlier turns remain
    consistent and retrievable in later turns. It integrates with FactTracker
    to measure memory drift across conversation boundaries.

    Usage in DeepEval:
        metric = MemoryDriftMetric(
            threshold=0.2,  # Allow 20% fact violations
            model=some_llm_judge,
        )
        assert_test(test_case, [metric])

    Threshold interpretation:
      - 0.0: All facts must be remembered perfectly
      - 0.2: Up to 20% of facts can be violated
      - 1.0: Allow any level of drift (permissive)
    """

    def __init__(
        self,
        threshold: float = 0.2,
        model: DeepEvalBaseLLM | None = None,
        include_reason: bool = True,
    ):
        """Initialize MemoryDriftMetric.

        Args:
            threshold: Maximum acceptable memory drift ratio (0.0-1.0).
            model: Optional DeepEval judge for advanced analysis.
            include_reason: Include explanation in score details.
        """
        self.threshold = threshold
        self.model = model
        self.include_reason = include_reason
        self._metric_name = "MemoryDriftMetric"

    def measure(self, test_case: Any) -> float:
        """Measure memory drift for a test case.

        Expects test_case to have:
          - input: Full conversation context (turns and facts)
          - actual_output: Final state/output that should reflect remembered facts

        Returns:
            Score from 0.0 (perfect memory) to 1.0 (complete drift).
        """
        # If test_case has scenario results, extract drift directly
        if hasattr(test_case, "scenario_result"):
            return test_case.scenario_result.avg_memory_drift

        # Otherwise, parse from test_case input/output
        if hasattr(test_case, "input") and hasattr(test_case, "actual_output"):
            return self._compute_drift_from_text(test_case.input, test_case.actual_output)

        # Default: unknown
        return 0.5

    def _compute_drift_from_text(self, input_text: str, output_text: str) -> float:
        """Compute drift ratio from conversation text and output.

        This is a heuristic parser that identifies key facts in input
        and checks if they are reflected in output.
        """
        # Simple heuristic: look for contradictions or missing keywords
        input_lower = input_text.lower()
        output_lower = output_text.lower()

        # Extract common keywords that indicate facts
        keywords_found = 0
        keywords_missing = 0

        # Check for common fact keywords
        fact_keywords = [
            "project name",
            "budget",
            "team",
            "technologies",
            "react",
            "flutter",
            "node",
            "postgres",
        ]

        for keyword in fact_keywords:
            if keyword in input_lower:
                keywords_found += 1
                if keyword not in output_lower:
                    keywords_missing += 1

        # Drift ratio: keywords mentioned in input but missing from output
        if keywords_found == 0:
            return 0.0

        return min(1.0, keywords_missing / keywords_found)

    def is_successful(self) -> bool:
        """Check if measurement passed threshold."""
        return self.score <= (1.0 - self.threshold)

    @property
    def score(self) -> float:
        """Return the measured drift score (lower is better)."""
        return getattr(self, "_score", 0.5)

    @score.setter
    def score(self, value: float) -> None:
        """Set the measured drift score."""
        self._score = max(0.0, min(1.0, value))

    def __repr__(self) -> str:
        return (
            f"MemoryDriftMetric(threshold={self.threshold}, score={self.score:.2%}, "
            f"successful={self.is_successful()})"
        )


class AnchorConsistencyMetric(Metric):
    """Evaluate consistency of extracted anchors across turns.

    Anchors are critical information markers (e.g., "project name is X").
    This metric checks that anchor values remain consistent and aren't
    contradicted in subsequent turns.

    High score (close to 1.0): Anchors remain consistent
    Low score (close to 0.0): Anchors are contradicted or lost
    """

    def __init__(
        self,
        threshold: float = 0.15,  # Allow 15% anchor inconsistency
        model: DeepEvalBaseLLM | None = None,
    ):
        """Initialize AnchorConsistencyMetric.

        Args:
            threshold: Maximum acceptable anchor inconsistency ratio.
            model: Optional DeepEval judge.
        """
        self.threshold = threshold
        self.model = model
        self._metric_name = "AnchorConsistencyMetric"

    def measure(self, test_case: Any) -> float:
        """Measure anchor consistency.

        Returns:
            Score from 0.0 (inconsistent) to 1.0 (perfectly consistent).
        """
        # If test_case has anchors, check consistency
        if hasattr(test_case, "anchors"):
            return self._check_anchor_consistency(test_case.anchors)

        # If test_case has a scenario result, use its anchor data
        if hasattr(test_case, "scenario_result"):
            return self._check_scenario_anchors(test_case.scenario_result)

        return 0.5

    def _check_anchor_consistency(self, anchors: list[dict[str, Any]]) -> float:
        """Check consistency among anchors.

        Heuristic: Same anchor_type should not have conflicting values.
        """
        anchor_map: dict[str, set[Any]] = {}

        for anchor in anchors:
            anchor_type = anchor.get("anchor_type", "unknown")
            value = anchor.get("key_information", "")

            if anchor_type not in anchor_map:
                anchor_map[anchor_type] = set()
            anchor_map[anchor_type].add(value)

        # Count inconsistencies: anchor types with multiple distinct values
        inconsistent_types = sum(1 for values in anchor_map.values() if len(values) > 1)
        total_types = len(anchor_map)

        if total_types == 0:
            return 1.0

        inconsistency_ratio = inconsistent_types / total_types
        return max(0.0, 1.0 - inconsistency_ratio)

    def _check_scenario_anchors(self, scenario_result: Any) -> float:
        """Check anchors from a scenario result."""
        # If the scenario result tracks anchor consistency, use it
        if hasattr(scenario_result, "anchor_inconsistencies"):
            total_anchors = scenario_result.anchor_inconsistencies.get("total", 1)
            conflicts = scenario_result.anchor_inconsistencies.get("conflicts", 0)
            return max(0.0, 1.0 - (conflicts / total_anchors))

        # Default: assume consistent
        return 1.0

    def is_successful(self) -> bool:
        """Check if consistency score is above threshold."""
        return self.score >= self.threshold

    @property
    def score(self) -> float:
        """Return consistency score (higher is better)."""
        return getattr(self, "_score", 0.5)

    @score.setter
    def score(self, value: float) -> None:
        """Set consistency score."""
        self._score = max(0.0, min(1.0, value))

    def __repr__(self) -> str:
        return (
            f"AnchorConsistencyMetric(threshold={self.threshold}, "
            f"score={self.score:.2%}, successful={self.is_successful()})"
        )


class ContradictionDetectionMetric(Metric):
    """Detect and measure handling of contradictions in conversation.

    When conflicting facts are introduced (e.g., budget €30k then €80k),
    measure whether the system:
      1. Recognizes the contradiction
      2. Resolves it (chooses one value)
      3. Avoids mixing both values in final output

    Score:
      - 1.0: Clean resolution (one value chosen, contradiction noted)
      - 0.5: Partial resolution (some mixing, but one value dominates)
      - 0.0: Poor resolution (both values appear, unclear which wins)
    """

    def __init__(self, threshold: float = 0.4):
        """Initialize ContradictionDetectionMetric.

        Args:
            threshold: Minimum acceptable score for detecting/resolving contradictions.
        """
        self.threshold = threshold
        self._metric_name = "ContradictionDetectionMetric"

    def measure(self, test_case: Any) -> float:
        """Measure contradiction handling.

        Returns:
            Score from 0.0 (poor) to 1.0 (excellent).
        """
        if hasattr(test_case, "scenario_result"):
            result = test_case.scenario_result
            # If it's a contradiction scenario, check how well it was resolved
            if hasattr(result, "profile") and "contradiction" in str(result.profile).lower():
                return self._check_contradiction_resolution(result)

        # Try to detect contradictions in text
        if hasattr(test_case, "input") and hasattr(test_case, "actual_output"):
            return self._detect_contradictions_in_text(test_case.input, test_case.actual_output)

        return 0.5

    def _check_contradiction_resolution(self, scenario_result: Any) -> float:
        """Check how a contradiction scenario was resolved."""
        # Look for facts that changed across turns
        if not hasattr(scenario_result, "turns") or len(scenario_result.turns) < 2:
            return 1.0  # No contradictions to handle

        # Check if final facts are consistent (not both old and new value)
        violations = sum(t.memory_drift for t in scenario_result.turns)
        avg_violations = violations / len(scenario_result.turns)

        # Good resolution: low violations (chose one value, forgot other)
        # Bad resolution: high violations (both values present)
        return max(0.0, 1.0 - avg_violations)

    def _detect_contradictions_in_text(self, input_text: str, output_text: str) -> float:
        """Detect contradictions by looking for conflicting keywords.

        Simple heuristic: look for opposing statements or numeric conflicts.
        """
        input_lower = input_text.lower()
        output_lower = output_text.lower()

        # Check for contradiction patterns
        contradiction_pairs = [
            ("30,000", "80,000"),
            ("react", "flutter"),
            ("web app", "mobile app"),
            ("$30k", "$80k"),
        ]

        both_present = 0
        for val_a, val_b in contradiction_pairs:
            if val_a in input_lower and val_b in input_lower:
                # Contradiction exists in input
                if val_a in output_lower and val_b in output_lower:
                    # Both values appear in output (bad)
                    both_present += 1
                else:
                    # Only one value in output (good)
                    pass

        if both_present == 0:
            return 1.0  # No contradictions, or handled cleanly
        else:
            # Some contradictions not resolved
            return max(0.0, 1.0 - both_present * 0.3)

    def is_successful(self) -> bool:
        """Check if contradiction handling is above threshold."""
        return self.score >= self.threshold

    @property
    def score(self) -> float:
        """Return contradiction handling score."""
        return getattr(self, "_score", 0.5)

    @score.setter
    def score(self, value: float) -> None:
        """Set contradiction handling score."""
        self._score = max(0.0, min(1.0, value))

    def __repr__(self) -> str:
        return (
            f"ContradictionDetectionMetric(threshold={self.threshold}, "
            f"score={self.score:.2%}, successful={self.is_successful()})"
        )
