"""Citation validation and coherence repair for RAG generation.

Validates that all source_ids referenced in the estimation exist in retrieved chunks.
Repairs or rejects estimations with dangling or missing citations.
"""

from __future__ import annotations

import re
import structlog

from app.generation.rag.schemas import (
    EstimateModule,
    EstimateTask,
    RagPipelineEstimate,
    RetrievedChunk,
)

log = structlog.get_logger(__name__)


class CitationValidatorService:
    """Validate and repair citations in generated estimates."""

    def __init__(self) -> None:
        """Initialize the validator."""
        pass

    def validate_citations(
        self,
        estimate: RagPipelineEstimate,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[RagPipelineEstimate, list[str]]:
        """Validate that all sources referenced in estimate exist in retrieved chunks.

        Returns:
            (estimate_with_valid_sources, validation_warnings)
        """
        valid_source_ids = {chunk.source_id for chunk in retrieved_chunks}
        estimate_source_ids = self._extract_source_ids_from_estimate(estimate)

        warnings: list[str] = []
        missing_sources = estimate_source_ids - valid_source_ids

        if missing_sources:
            warnings.append(f"Missing sources referenced: {missing_sources}")
            # Remove dangling sources from assumptions
            estimate = self._repair_sources_in_estimate(estimate, valid_source_ids)

        return (estimate, warnings)

    def _extract_source_ids_from_estimate(self, estimate: RagPipelineEstimate) -> set[str]:
        """Extract all source_ids mentioned in estimate text fields."""
        sources: set[str] = set()

        # Extract from explicit sources list
        if estimate.sources:
            sources.update(estimate.sources)

        # Extract from summary (pattern: [src-123] or src-123)
        sources.update(self._extract_source_references(estimate.summary))

        # Extract from assumptions
        for assumption in estimate.assumptions:
            sources.update(self._extract_source_references(assumption))

        return sources

    def _extract_source_references(self, text: str) -> set[str]:
        """Extract all source references from text using regex."""
        # Match patterns: [src-123], [source-456], src-789, etc.
        pattern = r"\[?(src(?:-\d+)?\]?|source(?:-\d+)?\]?)"
        matches = re.findall(pattern, text, re.IGNORECASE)
        return {match.strip("[]") for match in matches if match}

    def _repair_sources_in_estimate(
        self,
        estimate: RagPipelineEstimate,
        valid_sources: set[str],
    ) -> RagPipelineEstimate:
        """Remove references to invalid sources from estimate fields."""
        # Clean sources list
        cleaned_sources = [src for src in estimate.sources if src in valid_sources]

        # Clean assumptions by removing references to invalid sources
        cleaned_assumptions = [
            self._remove_invalid_source_refs(assumption, valid_sources)
            for assumption in estimate.assumptions
        ]

        return RagPipelineEstimate(
            summary=estimate.summary,
            low_confidence=estimate.low_confidence,
            modules=estimate.modules,
            assumptions=cleaned_assumptions,
            sources=cleaned_sources,
        )

    def _remove_invalid_source_refs(self, text: str, valid_sources: set[str]) -> str:
        """Remove references to invalid sources from text."""
        # Replace [invalid-src] with empty string, keep [valid-src]
        pattern = r"\[src-\d+\]"
        matches = re.finditer(pattern, text)
        offset = 0
        result = text

        for match in matches:
            src_ref = match.group(0)
            if src_ref not in valid_sources:
                start = match.start() - offset
                end = match.end() - offset
                result = result[:start] + result[end:]
                offset += end - start

        return result.strip()

    def score_citation_quality(
        self,
        estimate: RagPipelineEstimate,
        retrieved_chunks: list[RetrievedChunk],
    ) -> float:
        """Score citation quality (0.0 to 1.0).

        Higher score = more citations are valid and present.
        """
        if not estimate.sources:
            return 0.5  # Neutral if no sources claimed

        valid_source_ids = {chunk.source_id for chunk in retrieved_chunks}
        valid_count = sum(1 for src in estimate.sources if src in valid_source_ids)

        return min(1.0, valid_count / max(1, len(estimate.sources)))

    def is_coherent(self, estimate: RagPipelineEstimate) -> bool:
        """Check basic coherence rules.

        Returns False if:
        - Engineer days sum to 0
        - No modules defined
        - No assumptions
        """
        if not estimate.modules:
            log.warning("coherence_check_failed", reason="no_modules")
            return False

        total_days = sum(
            module.engineer_days + sum(task.engineer_days for task in module.tasks)
            for module in estimate.modules
        )

        if total_days <= 0:
            log.warning("coherence_check_failed", reason="zero_engineer_days")
            return False

        if not estimate.assumptions:
            log.warning("coherence_check_failed", reason="no_assumptions")
            return False

        return True
