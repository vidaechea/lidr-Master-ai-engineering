"""Tests for CoherenceRepairService."""

import pytest

from app.generation.rag.coherence_repair_service import CoherenceRepairService
from app.generation.rag.schemas import (
    EstimateModule,
    EstimateTask,
    RagPipelineEstimate,
)


@pytest.fixture
def service():
    """Fixture for coherence repair service."""
    return CoherenceRepairService()


@pytest.fixture
def valid_estimate():
    """Fixture for valid estimate."""
    return RagPipelineEstimate(
        summary="Valid estimate",
        low_confidence=False,
        modules=[
            EstimateModule(
                name="Module 1",
                engineer_days=5.0,
                tasks=[EstimateTask(name="Task 1", engineer_days=5.0)],
            )
        ],
        assumptions=["Assumption 1"],
        sources=[],
    )


class TestCoherenceRepair:
    """Unit tests for coherence repair."""

    def test_repair_valid_estimate_no_changes(self, service, valid_estimate):
        """Test that valid estimate is not repaired."""
        repaired, repairs = service.repair(valid_estimate)

        assert len(repairs) == 0
        assert repaired.summary == valid_estimate.summary

    def test_repair_zero_engineer_days(self, service):
        """Test repair for zero engineer days."""
        estimate = RagPipelineEstimate(
            summary="Zero effort estimate",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module",
                    engineer_days=0.0,
                    tasks=[EstimateTask(name="Task", engineer_days=0.0)],
                )
            ],
            assumptions=["Assumption"],
            sources=[],
        )

        repaired, repairs = service.repair(estimate)

        assert "added_minimal_engineer_days" in repairs
        assert repaired.modules[0].engineer_days > 0

    def test_repair_adds_default_assumptions(self, service):
        """Test that default assumptions are added when missing."""
        estimate = RagPipelineEstimate(
            summary="No assumptions",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module",
                    engineer_days=1.0,
                    tasks=[EstimateTask(name="Task", engineer_days=1.0)],
                )
            ],
            assumptions=[],
            sources=[],
        )

        repaired, repairs = service.repair(estimate)

        assert "added_default_assumptions" in repairs
        assert len(repaired.assumptions) > 0
        assert repaired.low_confidence is True  # Marked as low confidence

    def test_repair_adds_default_module(self, service):
        """Test that default module is added when missing."""
        estimate = RagPipelineEstimate(
            summary="No modules",
            low_confidence=False,
            modules=[],
            assumptions=["Assumption"],
            sources=[],
        )

        repaired, repairs = service.repair(estimate)

        assert "added_default_module" in repairs
        assert len(repaired.modules) > 0
        assert repaired.modules[0].name == "Core Work"
        assert repaired.low_confidence is True  # Marked as low confidence

    def test_repair_multiple_issues(self, service):
        """Test repair handles multiple issues."""
        estimate = RagPipelineEstimate(
            summary="Multiple issues",
            low_confidence=False,
            modules=[],
            assumptions=[],
            sources=[],
        )

        repaired, repairs = service.repair(estimate)

        assert len(repairs) == 3  # All three repairs applied
        assert "added_default_module" in repairs
        assert "added_default_assumptions" in repairs

    def test_repair_minimal_effort_is_one_day(self, service):
        """Test that minimal effort repair adds exactly 1 day."""
        estimate = RagPipelineEstimate(
            summary="Zero effort",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module",
                    engineer_days=0.0,
                    tasks=[],
                )
            ],
            assumptions=["Assumption"],
            sources=[],
        )

        repaired, repairs = service.repair(estimate)

        assert repaired.modules[0].engineer_days == 1.0

    def test_repair_default_module_has_tasks(self, service):
        """Test that default module includes tasks."""
        estimate = RagPipelineEstimate(
            summary="No modules",
            low_confidence=False,
            modules=[],
            assumptions=["Assumption"],
            sources=[],
        )

        repaired, repairs = service.repair(estimate)

        default_module = repaired.modules[0]
        assert len(default_module.tasks) > 0
        assert all(isinstance(task, EstimateTask) for task in default_module.tasks)

    def test_repair_preserves_valid_data(self, service):
        """Test that repair preserves valid estimate data."""
        estimate = RagPipelineEstimate(
            summary="Estimate with some valid data",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Valid Module",
                    engineer_days=5.0,
                    tasks=[EstimateTask(name="Valid Task", engineer_days=5.0)],
                )
            ],
            assumptions=[],
            sources=["src-1"],
        )

        repaired, repairs = service.repair(estimate)

        # Summary and valid module preserved
        assert repaired.summary == estimate.summary
        assert repaired.sources == estimate.sources
        # Only assumptions added
        assert "added_default_assumptions" in repairs
        assert repaired.modules[0].name == "Valid Module"
