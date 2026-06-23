"""Tests for CitationValidatorService."""

import pytest

from app.generation.rag.citation_validator_service import CitationValidatorService
from app.generation.rag.schemas import (
    EstimateModule,
    EstimateTask,
    RagPipelineEstimate,
    RetrievedChunk,
)


@pytest.fixture
def service():
    """Fixture for citation validator."""
    return CitationValidatorService()


@pytest.fixture
def sample_chunks():
    """Fixture for sample retrieved chunks."""
    return [
        RetrievedChunk(
            source_id="src-1",
            chunk_id=1,
            document_id=1,
            chunk_type="budget_component",
            content="Content for chunk 1",
            distance=0.1,
            metadata={"year": "2023"},
        ),
        RetrievedChunk(
            source_id="src-2",
            chunk_id=2,
            document_id=1,
            chunk_type="budget_component",
            content="Content for chunk 2",
            distance=0.2,
            metadata={"year": "2024"},
        ),
    ]


@pytest.fixture
def sample_estimate():
    """Fixture for sample estimate."""
    return RagPipelineEstimate(
        summary="Estimate for project [src-1] and [src-2]",
        low_confidence=False,
        modules=[
            EstimateModule(
                name="Module 1",
                engineer_days=5.0,
                tasks=[EstimateTask(name="Task 1", engineer_days=5.0)],
            )
        ],
        assumptions=["Based on src-1 and src-2"],
        sources=["src-1", "src-2"],
    )


class TestCitationValidator:
    """Unit tests for citation validation."""

    def test_validate_citations_all_valid(self, service, sample_estimate, sample_chunks):
        """Test validation with all valid citations."""
        estimate, warnings = service.validate_citations(sample_estimate, sample_chunks)

        assert len(warnings) == 0
        assert estimate.sources == ["src-1", "src-2"]

    def test_validate_citations_missing_source(self, service, sample_estimate, sample_chunks):
        """Test validation with missing source."""
        # Add invalid source to estimate
        sample_estimate.sources.append("src-999")
        sample_estimate.assumptions.append("Reference to [src-999]")

        estimate, warnings = service.validate_citations(sample_estimate, sample_chunks)

        assert len(warnings) > 0
        assert "src-999" not in estimate.sources

    def test_validate_citations_repairs_sources(self, service, sample_chunks):
        """Test that invalid sources are removed during repair."""
        estimate = RagPipelineEstimate(
            summary="Test [src-1] and [src-invalid]",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module",
                    engineer_days=1.0,
                    tasks=[EstimateTask(name="Task", engineer_days=1.0)],
                )
            ],
            assumptions=["Uses src-1"],
            sources=["src-1", "src-invalid"],
        )

        repaired, warnings = service.validate_citations(estimate, sample_chunks)

        assert "src-invalid" not in repaired.sources
        assert "src-1" in repaired.sources

    def test_extract_source_references_bracket_format(self, service):
        """Test extracting source references in bracket format."""
        text = "Based on [src-123] and [src-456] analysis"
        sources = service._extract_source_references(text)

        assert "src-123" in sources
        assert "src-456" in sources

    def test_extract_source_references_plain_format(self, service):
        """Test extracting plain source references."""
        text = "According to src-789 documentation"
        sources = service._extract_source_references(text)

        assert any("src" in s and "789" in s for s in sources)

    def test_is_coherent_valid_estimate(self, service, sample_estimate):
        """Test coherence check for valid estimate."""
        assert service.is_coherent(sample_estimate) is True

    def test_is_coherent_no_modules(self, service):
        """Test coherence check fails with no modules."""
        estimate = RagPipelineEstimate(
            summary="No modules",
            low_confidence=False,
            modules=[],
            assumptions=["Assumption"],
            sources=[],
        )

        assert service.is_coherent(estimate) is False

    def test_is_coherent_zero_engineer_days(self, service):
        """Test coherence check fails with zero engineer days."""
        estimate = RagPipelineEstimate(
            summary="Zero effort",
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

        assert service.is_coherent(estimate) is False

    def test_is_coherent_no_assumptions(self, service, sample_estimate):
        """Test coherence check fails with no assumptions."""
        sample_estimate.assumptions = []
        assert service.is_coherent(sample_estimate) is False

    def test_score_citation_quality_all_valid(self, service, sample_estimate, sample_chunks):
        """Test citation quality scoring for all valid citations."""
        score = service.score_citation_quality(sample_estimate, sample_chunks)

        assert 0.0 <= score <= 1.0
        assert score == 1.0  # All sources valid

    def test_score_citation_quality_partial_valid(self, service, sample_chunks):
        """Test citation quality scoring with partial valid citations."""
        estimate = RagPipelineEstimate(
            summary="Test",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module",
                    engineer_days=1.0,
                    tasks=[EstimateTask(name="Task", engineer_days=1.0)],
                )
            ],
            assumptions=[],
            sources=["src-1", "src-invalid"],
        )

        score = service.score_citation_quality(estimate, sample_chunks)

        assert 0.0 < score < 1.0  # Partial score

    def test_score_citation_quality_no_sources(self, service, sample_chunks):
        """Test citation quality scoring with no sources."""
        estimate = RagPipelineEstimate(
            summary="Test",
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

        score = service.score_citation_quality(estimate, sample_chunks)

        assert score == 0.5  # Neutral when no sources claimed
