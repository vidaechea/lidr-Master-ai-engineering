"""Structured query reformulation for RAG retrieval.

Distills raw transcript into structured EstimationQuery with keywords,
normalized search text, and optional sector/year filters. Includes fallback
path when structured extraction fails.
"""

from __future__ import annotations

import re
import structlog

from app.generation.rag.schemas import EstimationQuery

log = structlog.get_logger(__name__)


class QueryReformulationService:
    """Convert raw transcript into structured EstimationQuery."""

    def __init__(self) -> None:
        """Initialize the reformulation service."""
        pass

    def reformulate(self, transcript: str) -> EstimationQuery:
        """Distill transcript into structured query with keywords and search text.

        Falls back to keyword extraction if structured extraction fails.
        """
        normalized = self._normalize_text(transcript)
        keywords = self._extract_keywords(normalized)
        search_text = self._compose_search_text(keywords, normalized)

        # Optional: extract sector/year hints from metadata if present.
        # For now, leave these as None (caller can override if needed).
        sector = self._extract_sector_hint(transcript)
        year_from, year_to = self._extract_year_range(transcript)
        year_from, year_to = self._sanitize_year_range(year_from, year_to)

        query = EstimationQuery(
            search_text=search_text,
            sector=sector,
            year_from=year_from,
            year_to=year_to,
            chunk_types=["budget_component"],  # Default for budget corpus
            keywords=keywords,
        )

        log.debug(
            "query_reformulated",
            keywords_count=len(keywords),
            has_sector=sector is not None,
            has_year_range=year_from is not None or year_to is not None,
        )
        return query

    def _sanitize_year_range(
        self,
        year_from: int | None,
        year_to: int | None,
    ) -> tuple[int | None, int | None]:
        """Return a safe year range compatible with EstimationQuery constraints.

        Guards against malformed numeric captures (e.g. trailing IDs like 0005)
        and normalizes inverted ranges.
        """
        valid_from = self._sanitize_year_value(year_from)
        valid_to = self._sanitize_year_value(year_to)

        if valid_from is not None and valid_to is not None and valid_from > valid_to:
            return (valid_to, valid_from)

        return (valid_from, valid_to)

    def _sanitize_year_value(self, value: int | None) -> int | None:
        """Keep only years within supported EstimationQuery bounds."""
        if value is None:
            return None
        if 2000 <= value <= 2100:
            return value
        return None

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace and deduplicate spaces."""
        return " ".join(text.split())

    def _extract_keywords(self, text: str, min_length: int = 4, max_keywords: int = 12) -> list[str]:
        """Extract meaningful keywords from text.

        Filter out common words, keep min_length+ tokens, deduplicate.
        """
        # Remove punctuation and split
        words = [word.strip(".,:;()[]{}\"'").lower() for word in text.split()]

        # Filter: lowercase, min length, not numbers-only, not single char
        filtered = [
            word
            for word in words
            if len(word) >= min_length and not word.isdigit() and word.isalpha()
        ]

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for word in filtered:
            if word not in seen:
                seen.add(word)
                unique.append(word)
                if len(unique) >= max_keywords:
                    break

        return unique

    def _compose_search_text(self, keywords: list[str], normalized: str) -> str:
        """Compose compact search text from keywords or fallback."""
        if keywords:
            # Use top keywords for search
            return " ".join(keywords[:8])
        else:
            # Fallback: use first N characters of normalized transcript
            return normalized[:220]

    def _extract_sector_hint(self, text: str) -> str | None:
        """Try to detect sector hint from keywords or metadata in transcript.

        This is a simple heuristic; can be extended with NLP.
        """
        text_lower = text.lower()
        sector_keywords = {
            "saas": ["saas", "software as a service", "subscription platform"],
            "fintech": ["bank", "payment", "financial", "crypto"],
            "healthcare": ["hospital", "patient", "medical", "health"],
            "retail": ["store", "ecommerce", "product catalog", "checkout"],
            "manufacturing": ["factory", "production", "supply", "inventory"],
        }

        for sector, keywords_list in sector_keywords.items():
            if any(keyword in text_lower for keyword in keywords_list):
                return sector

        return None

    def _extract_year_range(self, text: str) -> tuple[int | None, int | None]:
        """Try to extract year range from text (e.g., "2023-2025" or "from 2022").

        Returns (year_from, year_to) or (None, None) if not found.
        """
        year_from = None
        year_to = None

        # Match patterns like "2023-2025" or "2023 to 2025"
        range_match = re.search(r"(\d{4})\s*(?:-|to|until)\s*(\d{4})", text)
        if range_match:
            year_from = int(range_match.group(1))
            year_to = int(range_match.group(2))
            return self._sanitize_year_range(year_from, year_to)

        # Match single year like "2023" or "in 2023"
        single_match = re.search(r"(?:in|from|since)\s+(\d{4})", text)
        if single_match:
            year = int(single_match.group(1))
            safe_year = self._sanitize_year_value(year)
            if safe_year is not None:
                year_from = safe_year
                # Assume +5 year buffer, clamped to schema upper bound.
                year_to = min(safe_year + 5, 2100)
                return (year_from, year_to)

        return (year_from, year_to)
