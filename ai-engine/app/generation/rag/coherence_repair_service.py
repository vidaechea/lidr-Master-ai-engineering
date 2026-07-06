"""Coherence repair for RAG generation.

Attempts to repair estimations that fail coherence checks, such as:
- Zero engineer days estimates
- Missing assumptions
- Malformed module/task structures
"""

from __future__ import annotations

import structlog

from app.generation.rag.schemas import (
    EstimateModule,
    EstimateTask,
    RagPipelineEstimate,
)

log = structlog.get_logger(__name__)


class CoherenceRepairService:
    """Repair incoherent or malformed estimates."""

    def __init__(self) -> None:
        """Initialize the repair service."""
        pass

    def repair(self, estimate: RagPipelineEstimate) -> tuple[RagPipelineEstimate, list[str]]:
        """Attempt to repair incoherent estimate.

        Returns:
            (repaired_estimate, list_of_repairs_applied)
        """
        repairs: list[str] = []

        # Check and fix zero engineer days
        if self._has_zero_engineer_days(estimate):
            estimate = self._add_minimal_effort(estimate)
            repairs.append("added_minimal_engineer_days")

        # Check and fix missing assumptions
        if not estimate.assumptions:
            estimate = self._add_default_assumptions(estimate)
            repairs.append("added_default_assumptions")

        # Check and fix empty modules
        if not estimate.modules:
            estimate = self._add_default_module(estimate)
            repairs.append("added_default_module")

        log.info("coherence_repair_applied", repairs_count=len(repairs), repairs=repairs)
        return (estimate, repairs)

    def _has_zero_engineer_days(self, estimate: RagPipelineEstimate) -> bool:
        """Check if total engineer days is <= 0."""
        total = sum(
            module.engineer_days + sum(task.engineer_days for task in module.tasks)
            for module in estimate.modules
        )
        return total <= 0

    def _add_minimal_effort(self, estimate: RagPipelineEstimate) -> RagPipelineEstimate:
        """Add minimal (1 day) effort to first module if all zeros."""
        if not estimate.modules:
            return estimate

        repaired_modules = []
        for i, module in enumerate(estimate.modules):
            if i == 0 and module.engineer_days == 0:
                # Add 1 day to first module
                repaired_modules.append(
                    EstimateModule(
                        name=module.name,
                        engineer_days=1.0,
                        tasks=module.tasks,
                    )
                )
            else:
                repaired_modules.append(module)

        return RagPipelineEstimate(
            summary=estimate.summary,
            estimate_markdown=estimate.estimate_markdown,
            low_confidence=estimate.low_confidence,
            modules=repaired_modules,
            line_items=estimate.line_items,
            assumptions=estimate.assumptions,
            sources=estimate.sources,
        )

    def _add_default_assumptions(self, estimate: RagPipelineEstimate) -> RagPipelineEstimate:
        """Add default assumptions if missing."""
        default_assumptions = [
            "Estimate based on available budget documentation",
            "Assumptions derived from provided transcripts and sources",
        ]

        return RagPipelineEstimate(
            summary=estimate.summary,
            estimate_markdown=estimate.estimate_markdown,
            low_confidence=True,  # Mark as low confidence since we added defaults
            modules=estimate.modules,
            line_items=estimate.line_items,
            assumptions=default_assumptions,
            sources=estimate.sources,
        )

    def _add_default_module(self, estimate: RagPipelineEstimate) -> RagPipelineEstimate:
        """Add a default module if none exist."""
        default_module = EstimateModule(
            name="Core Work",
            engineer_days=1.0,
            tasks=[
                EstimateTask(name="Analysis", engineer_days=0.5),
                EstimateTask(name="Implementation", engineer_days=0.5),
            ],
        )

        return RagPipelineEstimate(
            summary=estimate.summary,
            estimate_markdown=estimate.estimate_markdown,
            low_confidence=True,  # Mark as low confidence
            modules=[default_module],
            line_items=estimate.line_items,
            assumptions=estimate.assumptions,
            sources=estimate.sources,
        )
