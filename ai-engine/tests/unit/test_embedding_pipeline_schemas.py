from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.schemas import (
    BudgetComponent,
    Budget,
    Chunk,
    ClientMetadata,
    EmbeddedChunk,
    IngestRequest,
    IngestResponse,
    IngestStats,
)


class TestClientMetadata:
    """Tests for ClientMetadata model."""

    def test_valid_client_metadata(self) -> None:
        client = ClientMetadata(name="Acme Corp", sector="saas", country="ES")
        assert client.name == "Acme Corp"
        assert client.sector == "saas"
        assert client.country == "ES"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ClientMetadata(name="", sector="saas", country="ES")
        assert "at least 1 character" in str(exc_info.value).lower()

    def test_rejects_invalid_sector(self) -> None:
        with pytest.raises(ValidationError):
            ClientMetadata(name="Test", sector="invalid_sector", country="ES")

    def test_rejects_invalid_country_code(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ClientMetadata(name="Test", sector="saas", country="USA")
        assert "at most 2 characters" in str(exc_info.value).lower()

    def test_all_valid_sectors(self) -> None:
        sectors = ["saas", "manufacturing", "fintech", "distribution", "finance", "healthcare", "retail", "other"]
        for sector in sectors:
            client = ClientMetadata(name="Test", sector=sector, country="ES")  # type: ignore
            assert client.sector == sector


class TestBudgetComponent:
    """Tests for BudgetComponent model."""

    def test_valid_component(self) -> None:
        component = BudgetComponent(
            component_id="COMP-001",
            name="Discovery Phase",
            description="Requirements gathering",
            tech_stack=["python", "fastapi"],
            estimated_hours=40,
            complexity="medium",
            dependencies=[],
        )
        assert component.component_id == "COMP-001"
        assert component.estimated_hours == 40
        assert len(component.tech_stack) == 2

    def test_defaults_to_empty_tech_stack_and_dependencies(self) -> None:
        component = BudgetComponent(
            component_id="COMP-001",
            name="Discovery Phase",
            description="Requirements gathering",
            estimated_hours=40,
            complexity="medium",
        )
        assert component.tech_stack == []
        assert component.dependencies == []

    def test_rejects_zero_hours(self) -> None:
        with pytest.raises(ValidationError):
            BudgetComponent(
                component_id="COMP-001",
                name="Discovery Phase",
                description="Requirements gathering",
                estimated_hours=0,
                complexity="medium",
            )

    def test_rejects_negative_hours(self) -> None:
        with pytest.raises(ValidationError):
            BudgetComponent(
                component_id="COMP-001",
                name="Discovery Phase",
                description="Requirements gathering",
                estimated_hours=-10,
                complexity="medium",
            )

    def test_rejects_invalid_complexity(self) -> None:
        with pytest.raises(ValidationError):
            BudgetComponent(
                component_id="COMP-001",
                name="Discovery Phase",
                description="Requirements gathering",
                estimated_hours=40,
                complexity="extreme",  # type: ignore
            )

    def test_all_valid_complexity_levels(self) -> None:
        for complexity in ["low", "medium", "high"]:
            component = BudgetComponent(
                component_id="COMP-001",
                name="Phase",
                description="Description",
                estimated_hours=40,
                complexity=complexity,  # type: ignore
            )
            assert component.complexity == complexity


class TestBudget:
    """Tests for Budget model."""

    @pytest.fixture
    def sample_component(self) -> BudgetComponent:
        return BudgetComponent(
            component_id="DISC-001",
            name="Discovery Phase",
            description="Requirements gathering and analysis",
            tech_stack=["python", "fastapi"],
            estimated_hours=40,
            complexity="medium",
        )

    @pytest.fixture
    def sample_client(self) -> ClientMetadata:
        return ClientMetadata(name="Acme Corp", sector="saas", country="ES")

    def test_valid_budget(self, sample_client: ClientMetadata, sample_component: BudgetComponent) -> None:
        budget = Budget(
            budget_id="BUD-2024-001",
            client_metadata=sample_client,
            project_summary="SaaS platform development",
            main_technology="python",
            year=2024,
            total_estimated_hours=100,
            components=[sample_component],
        )
        assert budget.budget_id == "BUD-2024-001"
        assert budget.year == 2024
        assert len(budget.components) == 1

    def test_rejects_empty_components_list(self, sample_client: ClientMetadata) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Budget(
                budget_id="BUD-2024-001",
                client_metadata=sample_client,
                project_summary="SaaS platform development",
                main_technology="python",
                year=2024,
                total_estimated_hours=100,
                components=[],
            )
        assert "at least 1" in str(exc_info.value).lower()

    def test_rejects_invalid_year(self, sample_client: ClientMetadata, sample_component: BudgetComponent) -> None:
        with pytest.raises(ValidationError):
            Budget(
                budget_id="BUD-2024-001",
                client_metadata=sample_client,
                project_summary="SaaS platform development",
                main_technology="python",
                year=1999,  # Before 2000
                total_estimated_hours=100,
                components=[sample_component],
            )

    def test_rejects_zero_hours(self, sample_client: ClientMetadata, sample_component: BudgetComponent) -> None:
        with pytest.raises(ValidationError):
            Budget(
                budget_id="BUD-2024-001",
                client_metadata=sample_client,
                project_summary="SaaS platform development",
                main_technology="python",
                year=2024,
                total_estimated_hours=0,
                components=[sample_component],
            )


class TestChunk:
    """Tests for Chunk model."""

    def test_valid_chunk(self) -> None:
        chunk = Chunk(
            chunk_id="chunk_001",
            text="This is chunk text",
            metadata={"source": "budget", "budget_id": "BUD-001"},
            token_count=4,
        )
        assert chunk.chunk_id == "chunk_001"
        assert chunk.token_count == 4
        assert chunk.metadata["source"] == "budget"

    def test_defaults_to_empty_metadata(self) -> None:
        chunk = Chunk(chunk_id="chunk_001", text="Text", token_count=1)
        assert chunk.metadata == {}

    def test_rejects_empty_chunk_id(self) -> None:
        with pytest.raises(ValidationError):
            Chunk(chunk_id="", text="Text", token_count=1)

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValidationError):
            Chunk(chunk_id="chunk_001", text="", token_count=1)

    def test_rejects_negative_token_count(self) -> None:
        with pytest.raises(ValidationError):
            Chunk(chunk_id="chunk_001", text="Text", token_count=-1)


class TestEmbeddedChunk:
    """Tests for EmbeddedChunk model."""

    def test_valid_embedded_chunk(self) -> None:
        chunk = EmbeddedChunk(
            chunk_id="chunk_001",
            text="This is chunk text",
            metadata={"source": "budget"},
            token_count=4,
            embedding=[0.1, 0.2, 0.3],
        )
        assert chunk.chunk_id == "chunk_001"
        assert len(chunk.embedding) == 3
        assert chunk.embedding[0] == 0.1

    def test_embedding_can_be_large_vector(self) -> None:
        large_embedding = [float(i) / 1000 for i in range(1536)]  # OpenAI embedding size
        chunk = EmbeddedChunk(
            chunk_id="chunk_001",
            text="Text",
            token_count=1,
            embedding=large_embedding,
        )
        assert len(chunk.embedding) == 1536


class TestIngestStats:
    """Tests for IngestStats model."""

    def test_valid_stats(self) -> None:
        stats = IngestStats(
            total_budgets=5,
            total_chunks=50,
            total_tokens=5000,
            estimated_cost_usd=0.025,
        )
        assert stats.total_budgets == 5
        assert stats.estimated_cost_usd == 0.025

    def test_allows_zero_values(self) -> None:
        stats = IngestStats(
            total_budgets=0,
            total_chunks=0,
            total_tokens=0,
            estimated_cost_usd=0.0,
        )
        assert stats.total_budgets == 0

    def test_rejects_negative_values(self) -> None:
        with pytest.raises(ValidationError):
            IngestStats(
                total_budgets=-1,
                total_chunks=10,
                total_tokens=100,
                estimated_cost_usd=0.01,
            )


class TestIngestRequest:
    """Tests for IngestRequest model."""

    @pytest.fixture
    def sample_budget(self) -> Budget:
        client = ClientMetadata(name="Test Corp", sector="saas", country="ES")
        component = BudgetComponent(
            component_id="C-001",
            name="Phase",
            description="Desc",
            estimated_hours=40,
            complexity="medium",
        )
        return Budget(
            budget_id="BUD-001",
            client_metadata=client,
            project_summary="Project",
            main_technology="python",
            year=2024,
            total_estimated_hours=100,
            components=[component],
        )

    def test_valid_ingest_request(self, sample_budget: Budget) -> None:
        request = IngestRequest(budgets=[sample_budget])
        assert len(request.budgets) == 1
        assert request.budgets[0].budget_id == "BUD-001"

    def test_rejects_empty_budgets_list(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IngestRequest(budgets=[])
        assert "at least 1" in str(exc_info.value).lower()

    def test_multiple_budgets(self, sample_budget: Budget) -> None:
        request = IngestRequest(budgets=[sample_budget, sample_budget])
        assert len(request.budgets) == 2


class TestIngestResponse:
    """Tests for IngestResponse model."""

    def test_valid_ingest_response(self) -> None:
        chunk = EmbeddedChunk(
            chunk_id="chunk_001",
            text="Text",
            token_count=1,
            embedding=[0.1, 0.2],
        )
        stats = IngestStats(
            total_budgets=1,
            total_chunks=1,
            total_tokens=1,
            estimated_cost_usd=0.00001,
        )
        response = IngestResponse(chunks=[chunk], stats=stats)
        assert len(response.chunks) == 1
        assert response.stats.total_budgets == 1

    def test_response_with_multiple_chunks(self) -> None:
        chunks = [
            EmbeddedChunk(
                chunk_id=f"chunk_{i}",
                text=f"Text {i}",
                token_count=1,
                embedding=[0.1 * i],
            )
            for i in range(10)
        ]
        stats = IngestStats(
            total_budgets=1,
            total_chunks=10,
            total_tokens=10,
            estimated_cost_usd=0.00005,
        )
        response = IngestResponse(chunks=chunks, stats=stats)
        assert len(response.chunks) == 10


class TestSerialization:
    """Tests for JSON serialization/deserialization."""

    def test_budget_json_roundtrip(self) -> None:
        client = ClientMetadata(name="Acme", sector="saas", country="ES")
        component = BudgetComponent(
            component_id="C-001",
            name="Phase",
            description="Desc",
            estimated_hours=40,
            complexity="medium",
        )
        budget = Budget(
            budget_id="BUD-001",
            client_metadata=client,
            project_summary="Project",
            main_technology="python",
            year=2024,
            total_estimated_hours=100,
            components=[component],
        )

        json_str = budget.model_dump_json()
        restored = Budget.model_validate_json(json_str)

        assert restored.budget_id == budget.budget_id
        assert restored.client_metadata.name == budget.client_metadata.name
        assert len(restored.components) == len(budget.components)

    def test_ingest_response_json_roundtrip(self) -> None:
        chunk = EmbeddedChunk(
            chunk_id="chunk_001",
            text="Text",
            metadata={"key": "value"},
            token_count=5,
            embedding=[0.1, 0.2, 0.3],
        )
        stats = IngestStats(
            total_budgets=1,
            total_chunks=1,
            total_tokens=5,
            estimated_cost_usd=0.000025,
        )
        response = IngestResponse(chunks=[chunk], stats=stats)

        json_str = response.model_dump_json()
        restored = IngestResponse.model_validate_json(json_str)

        assert len(restored.chunks) == 1
        assert restored.chunks[0].chunk_id == "chunk_001"
        assert restored.stats.total_tokens == 5
