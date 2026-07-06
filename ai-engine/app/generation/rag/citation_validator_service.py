"""Citation validation and coherence repair for RAG generation.

Validates that all source_ids referenced in the estimation exist in retrieved chunks.
Repairs or rejects estimations with dangling or missing citations.
"""

from __future__ import annotations

import re
import structlog

from app.generation.rag.schemas import (
    EstimateLineItem,
    EstimateModule,
    EstimateTask,
    RagPipelineEstimate,
    RetrievedChunk,
    SourceReference,
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
        valid_chunk_refs = {
            (str(chunk.chunk_id), str(chunk.document_id)): chunk for chunk in retrieved_chunks
        }
        estimate_source_ids = self._extract_source_ids_from_estimate(estimate)

        warnings: list[str] = []
        missing_sources = estimate_source_ids - valid_source_ids

        if missing_sources:
            warnings.append(f"Missing sources referenced: {missing_sources}")
            estimate = self._repair_sources_in_estimate(estimate, valid_source_ids)

        estimate, line_item_warnings = self._repair_line_item_sources(estimate, valid_chunk_refs)
        warnings.extend(line_item_warnings)

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
            estimate_markdown=estimate.estimate_markdown,
            low_confidence=estimate.low_confidence,
            modules=estimate.modules,
            line_items=estimate.line_items,
            assumptions=cleaned_assumptions,
            sources=cleaned_sources,
        )

    def _repair_line_item_sources(
        self,
        estimate: RagPipelineEstimate,
        valid_chunk_refs: dict[tuple[str, str], RetrievedChunk],
    ) -> tuple[RagPipelineEstimate, list[str]]:
        warnings: list[str] = []
        repaired_line_items: list[EstimateLineItem] = []

        for line_item in estimate.line_items:
            repaired_line_item, line_warnings = self._repair_line_item(
                line_item,
                valid_chunk_refs,
            )
            repaired_line_items.append(repaired_line_item)
            warnings.extend(line_warnings)

        if repaired_line_items == estimate.line_items:
            return estimate, warnings

        return (
            RagPipelineEstimate(
                summary=estimate.summary,
                estimate_markdown=estimate.estimate_markdown,
                low_confidence=estimate.low_confidence or any(
                    not line_item.grounded for line_item in repaired_line_items
                ),
                modules=estimate.modules,
                line_items=repaired_line_items,
                assumptions=estimate.assumptions,
                sources=estimate.sources,
            ),
            warnings,
        )

    def _repair_line_item(
        self,
        line_item: EstimateLineItem,
        valid_chunk_refs: dict[tuple[str, str], RetrievedChunk],
    ) -> tuple[EstimateLineItem, list[str]]:
        valid_sources, invalid_pairs = self._partition_line_item_sources(
            line_item.sources,
            valid_chunk_refs,
        )
        warnings: list[str] = []

        if invalid_pairs:
            warnings.append(
                f"Invalid line item sources for {line_item.component}: {invalid_pairs}"
            )

        if line_item.grounded and not valid_sources:
            warnings.append(
                f"Downgraded line item '{line_item.component}' to insufficient context"
            )
            return (
                EstimateLineItem(
                    component=line_item.component,
                    hours=0.0,
                    rationale="Insufficient context to support this line item after citation validation.",
                    grounded=False,
                    sources=[],
                ),
                warnings,
            )

        if valid_sources != line_item.sources:
            return (
                EstimateLineItem(
                    component=line_item.component,
                    hours=line_item.hours,
                    rationale=line_item.rationale,
                    grounded=line_item.grounded,
                    sources=valid_sources,
                ),
                warnings,
            )

        return line_item, warnings

    def _partition_line_item_sources(
        self,
        sources: list[SourceReference],
        valid_chunk_refs: dict[tuple[str, str], RetrievedChunk],
    ) -> tuple[list[SourceReference], list[tuple[str, str]]]:
        valid_sources: list[SourceReference] = []
        invalid_pairs: list[tuple[str, str]] = []

        for source_ref in sources:
            ref_key = (source_ref.chunk_id, source_ref.document_id)
            if ref_key in valid_chunk_refs:
                valid_sources.append(source_ref)
            else:
                invalid_pairs.append(ref_key)

        return valid_sources, invalid_pairs

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
            line_item_sources = sum(len(line_item.sources) for line_item in estimate.line_items)
            if line_item_sources == 0:
                return 0.5  # Neutral if no sources claimed

        valid_source_ids = {chunk.source_id for chunk in retrieved_chunks}
        valid_chunk_refs = {
            (str(chunk.chunk_id), str(chunk.document_id)) for chunk in retrieved_chunks
        }
        valid_count = sum(1 for src in estimate.sources if src in valid_source_ids)
        total_claims = len(estimate.sources)

        for line_item in estimate.line_items:
            total_claims += len(line_item.sources)
            valid_count += sum(
                1
                for source_ref in line_item.sources
                if (source_ref.chunk_id, source_ref.document_id) in valid_chunk_refs
            )

        return min(1.0, valid_count / max(1, total_claims))

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
