"""Tests for QueryReformulationService."""

import pytest

from app.generation.rag.reformulation_service import QueryReformulationService
from app.generation.rag.schemas import EstimationQuery


@pytest.fixture
def service():
    """Fixture for reformulation service."""
    return QueryReformulationService()


class TestQueryReformulation:
    """Unit tests for query reformulation."""

    def test_reformulate_basic_transcript(self, service: QueryReformulationService):
        """Test basic transcript reformulation."""
        transcript = "We need to build a fintech payment system with three modules"
        query = service.reformulate(transcript)

        assert isinstance(query, EstimationQuery)
        assert len(query.search_text) > 0
        assert len(query.keywords) > 0
        assert "budget_component" in query.chunk_types

    def test_reformulate_extracts_keywords(self, service: QueryReformulationService):
        """Test keyword extraction from transcript."""
        transcript = "implementing authentication system with oauth2 and jwt tokens for security"
        query = service.reformulate(transcript)

        # Should extract meaningful keywords (4+ chars)
        assert any(keyword in query.keywords for keyword in ["implementing", "authentication", "system"])
        # Should not extract common short words
        assert "and" not in query.keywords
        assert "for" not in query.keywords

    def test_reformulate_detects_sector_fintech(self, service: QueryReformulationService):
        """Test sector detection for fintech."""
        transcript = "We process bank transfers and crypto payments daily"
        query = service.reformulate(transcript)

        assert query.sector == "fintech"

    def test_reformulate_detects_sector_healthcare(self, service: QueryReformulationService):
        """Test sector detection for healthcare."""
        transcript = "Patient records and hospital management system"
        query = service.reformulate(transcript)

        assert query.sector == "healthcare"

    def test_reformulate_detects_sector_retail(self, service: QueryReformulationService):
        """Test sector detection for retail."""
        transcript = "ecommerce platform with product catalog"
        query = service.reformulate(transcript)

        assert query.sector == "retail"

    def test_reformulate_prefers_explicit_saas_over_customer_terms(
        self,
        service: QueryReformulationService,
    ):
        """Explicit SaaS mentions should not be filtered as retail."""
        transcript = (
            "A B2B SaaS company needs an admin portal to manage existing customer "
            "accounts with SSO, audit log, RBAC, React, and PostgreSQL."
        )

        query = service.reformulate(transcript)

        assert query.sector == "saas"

    def test_reformulate_extracts_year_range_dash_format(self, service: QueryReformulationService):
        """Test year range extraction with dash format."""
        transcript = "Timeline from 2023-2025 for the project"
        query = service.reformulate(transcript)

        assert query.year_from == 2023
        assert query.year_to == 2025

    def test_reformulate_extracts_year_range_to_format(self, service: QueryReformulationService):
        """Test year range extraction with 'to' format."""
        transcript = "Project timeline 2022 to 2024"
        query = service.reformulate(transcript)

        assert query.year_from == 2022
        assert query.year_to == 2024

    def test_reformulate_extracts_single_year(self, service: QueryReformulationService):
        """Test single year extraction."""
        transcript = "Starting from 2023, we plan the implementation"
        query = service.reformulate(transcript)

        assert query.year_from == 2023
        assert query.year_to is not None  # Should have range buffer

    def test_reformulate_fallback_no_keywords(self, service: QueryReformulationService):
        """Test fallback when no valid keywords found."""
        transcript = "a b c d e"  # Too short for keyword extraction
        query = service.reformulate(transcript)

        # Should still have search_text (fallback to first 220 chars)
        assert len(query.search_text) > 0

    def test_reformulate_normalizes_whitespace(self, service: QueryReformulationService):
        """Test whitespace normalization."""
        transcript = "Build   a   system   with   multiple    spaces"
        query = service.reformulate(transcript)

        # Should have normalized search_text without extra spaces
        assert "   " not in query.search_text

    def test_reformulate_keyword_max_length(self, service: QueryReformulationService):
        """Test keyword list respects max length."""
        transcript = (
            "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 "
            "word11 word12 word13 word14 word15"
        )
        query = service.reformulate(transcript)

        # Should max out at 12 keywords
        assert len(query.keywords) <= 12

    def test_reformulate_deduplicates_keywords(self, service: QueryReformulationService):
        """Test keyword deduplication."""
        transcript = "system system system architecture architecture design"
        query = service.reformulate(transcript)

        # Should not have duplicates
        assert query.keywords.count("system") <= 1
        assert query.keywords.count("architecture") <= 1

    def test_reformulate_ignores_trailing_budget_sequence_as_year(
        self,
        service: QueryReformulationService,
    ):
        """Ensure legacy IDs like BUDGET-2024-0005 never produce year_to=5."""
        transcript = (
            "Presupuesto en curso BUDGET-2024-0005 para cliente legado. "
            "Tras la reunion del once de abril se amplia el alcance."
        )

        query = service.reformulate(transcript)

        assert query.year_from in (None, 2024)
        assert query.year_to is None or query.year_to >= 2000
