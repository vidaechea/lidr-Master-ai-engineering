from __future__ import annotations

import pytest

from app.embedding_pipeline.chunker import chunk_text, JSONStructuralChunker
from app.embedding_pipeline.schemas import Budget, BudgetComponent, ClientMetadata


def test_chunk_text_raises_when_overlap_is_not_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_overlap must be smaller than chunk_size"):
        chunk_text(text="abcdef", chunk_size=4, chunk_overlap=4)


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_chunk_text_returns_empty_for_blank_input(text: str) -> None:
    assert chunk_text(text=text, chunk_size=5, chunk_overlap=1) == []


def test_chunk_text_builds_expected_sliding_windows() -> None:
    result = chunk_text(text="abcdefghij", chunk_size=4, chunk_overlap=1)
    assert result == ["abcd", "defg", "ghij", "j"]


class TestJSONStructuralChunker:
    """Tests for JSONStructuralChunker."""

    @pytest.fixture
    def chunker(self) -> JSONStructuralChunker:
        """Create a chunker instance."""
        return JSONStructuralChunker()

    @pytest.fixture
    def sample_budget(self) -> Budget:
        """Create a sample budget for testing."""
        return Budget(
            budget_id="BUD-2024-001",
            client_metadata=ClientMetadata(
                name="Acme Corp",
                sector="saas",
                country="ES",
            ),
            project_summary="B2B SaaS platform with integrations",
            main_technology="nodejs",
            year=2024,
            total_estimated_hours=320,
            components=[
                BudgetComponent(
                    component_id="AUTH-001",
                    name="Authentication backend",
                    description="JWT-based authentication with OAuth2 integration",
                    tech_stack=["nodejs", "express", "jsonwebtoken"],
                    estimated_hours=80,
                    complexity="medium",
                    dependencies=[],
                ),
                BudgetComponent(
                    component_id="API-001",
                    name="REST API",
                    description="RESTful API endpoints for core business logic",
                    tech_stack=["nodejs", "express", "postgresql"],
                    estimated_hours=120,
                    complexity="high",
                    dependencies=["AUTH-001"],
                ),
            ],
        )

    def test_chunker_creates_one_chunk_per_component(self, chunker: JSONStructuralChunker, sample_budget: Budget) -> None:
        """Verify that one chunk is created per budget component."""
        chunks = chunker.chunk([sample_budget])
        assert len(chunks) == 2

    def test_chunk_id_format(self, chunker: JSONStructuralChunker, sample_budget: Budget) -> None:
        """Verify chunk_id format is {budget_id}::{component_id}."""
        chunks = chunker.chunk([sample_budget])
        assert chunks[0].chunk_id == "BUD-2024-001::AUTH-001"
        assert chunks[1].chunk_id == "BUD-2024-001::API-001"

    def test_chunk_text_includes_budget_context(self, chunker: JSONStructuralChunker, sample_budget: Budget) -> None:
        """Verify chunk text includes parent budget context."""
        chunks = chunker.chunk([sample_budget])
        text = chunks[0].text
        
        # Check for budget context
        assert "B2B SaaS platform with integrations" in text
        assert "saas" in text
        assert "2024" in text
        assert "nodejs" in text
        
        # Check for component details
        assert "Authentication backend" in text
        assert "JWT-based authentication with OAuth2 integration" in text
        assert "medium" in text
        assert "80" in text

    def test_chunk_text_tech_stack_formatting(self, chunker: JSONStructuralChunker, sample_budget: Budget) -> None:
        """Verify tech stack is properly formatted in chunk text."""
        chunks = chunker.chunk([sample_budget])
        text = chunks[0].text
        assert "nodejs, express, jsonwebtoken" in text

    def test_chunk_text_handles_empty_tech_stack(self, chunker: JSONStructuralChunker) -> None:
        """Verify chunk text handles components with empty tech stack."""
        budget = Budget(
            budget_id="BUD-2024-002",
            client_metadata=ClientMetadata(name="Test Corp", sector="fintech", country="US"),
            project_summary="Test project",
            main_technology="python",
            year=2024,
            total_estimated_hours=100,
            components=[
                BudgetComponent(
                    component_id="TEST-001",
                    name="Test component",
                    description="Test description",
                    tech_stack=[],
                    estimated_hours=40,
                    complexity="low",
                    dependencies=[],
                ),
            ],
        )
        chunks = chunker.chunk([budget])
        assert "Tech stack: N/A" in chunks[0].text

    def test_chunk_metadata_fields(self, chunker: JSONStructuralChunker, sample_budget: Budget) -> None:
        """Verify chunk metadata contains all required fields."""
        chunks = chunker.chunk([sample_budget])
        metadata = chunks[0].metadata
        
        assert metadata["budget_id"] == "BUD-2024-001"
        assert metadata["component_id"] == "AUTH-001"
        assert metadata["client_sector"] == "saas"
        assert metadata["main_technology"] == "nodejs"
        assert metadata["year"] == 2024
        assert metadata["complexity"] == "medium"
        assert metadata["estimated_hours"] == 80

    def test_token_count_is_calculated(self, chunker: JSONStructuralChunker, sample_budget: Budget) -> None:
        """Verify token count is calculated and positive."""
        chunks = chunker.chunk([sample_budget])
        assert chunks[0].token_count > 0
        assert isinstance(chunks[0].token_count, int)

    def test_multiple_budgets(self, chunker: JSONStructuralChunker) -> None:
        """Verify chunker handles multiple budgets correctly."""
        budget1 = Budget(
            budget_id="BUD-2024-001",
            client_metadata=ClientMetadata(name="Corp A", sector="saas", country="ES"),
            project_summary="Project A",
            main_technology="nodejs",
            year=2024,
            total_estimated_hours=100,
            components=[
                BudgetComponent(
                    component_id="COMP-001",
                    name="Component 1",
                    description="Description 1",
                    tech_stack=[],
                    estimated_hours=50,
                    complexity="low",
                    dependencies=[],
                ),
            ],
        )
        budget2 = Budget(
            budget_id="BUD-2024-002",
            client_metadata=ClientMetadata(name="Corp B", sector="fintech", country="US"),
            project_summary="Project B",
            main_technology="python",
            year=2024,
            total_estimated_hours=200,
            components=[
                BudgetComponent(
                    component_id="COMP-002",
                    name="Component 2",
                    description="Description 2",
                    tech_stack=[],
                    estimated_hours=100,
                    complexity="high",
                    dependencies=[],
                ),
            ],
        )
        
        chunks = chunker.chunk([budget1, budget2])
        assert len(chunks) == 2
        assert chunks[0].chunk_id == "BUD-2024-001::COMP-001"
        assert chunks[1].chunk_id == "BUD-2024-002::COMP-002"
