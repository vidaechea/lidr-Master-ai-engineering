from __future__ import annotations

import re

from app.generation.rag.schemas import (
    HallucinationLineReport,
    HallucinationReport,
    RagPipelineEstimate,
    RetrievedChunk,
)

_LABELED_HOURS_PATTERN = re.compile(
    r"(?:estimated\s+hours|hours?)\s*[:=]?\s*(\d+(?:[\.,]\d+)?)",
    re.IGNORECASE,
)
_SUFFIX_HOURS_PATTERN = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(?:hours?|h)\b", re.IGNORECASE)


def _extract_hour_values(text: str) -> list[float]:
    values: list[float] = []
    for pattern in (_LABELED_HOURS_PATTERN, _SUFFIX_HOURS_PATTERN):
        for match in pattern.findall(text):
            try:
                values.append(float(match.replace(",", ".")))
            except ValueError:
                continue
    deduped = sorted({round(value, 2) for value in values})
    return deduped


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _is_supported_by_evidence(estimate_line, chunk_map: dict[str, RetrievedChunk]) -> bool:
    expected_snippets = [_normalize_text(source.evidence) for source in estimate_line.sources if source.evidence]
    if not expected_snippets:
        return True

    chunk_text = " ".join(
        _normalize_text(chunk_map[source.chunk_id].content)
        for source in estimate_line.sources
        if source.chunk_id in chunk_map
    )
    if not chunk_text:
        return False
    return all(snippet in chunk_text for snippet in expected_snippets)


def gate_estimate(
    estimate: RagPipelineEstimate,
    kept_chunks: list[RetrievedChunk],
    *,
    tolerance: float,
    use_judge: bool,
) -> HallucinationReport:
    """Semantically verify grounded line items against cited chunk evidence."""
    chunk_map = {str(chunk.chunk_id): chunk for chunk in kept_chunks}
    lines: list[HallucinationLineReport] = []
    grounded_lines = 0
    degraded_lines = 0
    insufficient_lines = 0

    for line_item in estimate.line_items:
        cited_chunk_ids = [source.chunk_id for source in line_item.sources]
        if not line_item.grounded:
            insufficient_lines += 1
            lines.append(
                HallucinationLineReport(
                    component=line_item.component,
                    status="insufficient_context",
                    estimated_hours=line_item.hours,
                    anchored_hours=[],
                    cited_chunk_ids=cited_chunk_ids,
                    reason="Line already marked as insufficient context.",
                )
            )
            continue

        texts = [source.evidence for source in line_item.sources]
        texts.extend(chunk_map[chunk_id].content for chunk_id in cited_chunk_ids if chunk_id in chunk_map)
        anchored_hours = []
        for text in texts:
            anchored_hours.extend(_extract_hour_values(text))
        anchored_hours = sorted({round(value, 2) for value in anchored_hours})

        if not anchored_hours:
            degraded_lines += 1
            lines.append(
                HallucinationLineReport(
                    component=line_item.component,
                    status="degraded",
                    estimated_hours=line_item.hours,
                    anchored_hours=[],
                    cited_chunk_ids=cited_chunk_ids,
                    reason="No numeric anchor found in cited evidence.",
                )
            )
            continue

        allowed_delta = max(1.0, line_item.hours * tolerance)
        numeric_match = any(abs(line_item.hours - anchored) <= allowed_delta for anchored in anchored_hours)
        textual_match = _is_supported_by_evidence(line_item, chunk_map) if use_judge else True
        if numeric_match and textual_match:
            grounded_lines += 1
            lines.append(
                HallucinationLineReport(
                    component=line_item.component,
                    status="grounded",
                    estimated_hours=line_item.hours,
                    anchored_hours=anchored_hours,
                    cited_chunk_ids=cited_chunk_ids,
                    reason="Estimated hours stay within the configured evidence tolerance.",
                )
            )
            continue

        degraded_lines += 1
        reason = "Estimated hours diverge from cited numeric evidence."
        if numeric_match and not textual_match:
            reason = "Evidence snippet could not be matched back to the cited chunks."
        lines.append(
            HallucinationLineReport(
                component=line_item.component,
                status="degraded",
                estimated_hours=line_item.hours,
                anchored_hours=anchored_hours,
                cited_chunk_ids=cited_chunk_ids,
                reason=reason,
            )
        )

    return HallucinationReport(
        total_lines=len(estimate.line_items),
        grounded_lines=grounded_lines,
        degraded_lines=degraded_lines,
        insufficient_lines=insufficient_lines,
        lines=lines,
    )