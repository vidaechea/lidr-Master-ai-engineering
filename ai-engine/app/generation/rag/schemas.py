from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Generic Chunking & Embedding Schemas (backward compatible)
# ============================================================================


class ChunkRequest(BaseModel):
    """Request to split text into chunks."""

    text: str = Field(min_length=1)
    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=100, ge=0, le=2000)


class ChunkItem(BaseModel):
    """Single chunk with index."""

    index: int
    text: str


class ChunkResponse(BaseModel):
    """Response with list of chunks."""

    chunks: list[ChunkItem]


class EmbedRequest(BaseModel):
    """Request to embed texts."""

    texts: list[str] = Field(min_length=1)
    model: str = Field(default="text-embedding-3-small")


class EmbeddingItem(BaseModel):
    """Single embedding vector with index."""

    index: int
    vector: list[float]


class EmbedResponse(BaseModel):
    """Response with embeddings."""

    model: str
    embeddings: list[EmbeddingItem]


# ============================================================================
# Budget Schemas
# ============================================================================


class ClientMetadata(BaseModel):
    """Client information embedded in a budget."""

    name: str = Field(min_length=1, description="Client company name")
    sector: Literal[
        "saas",
        "manufacturing",
        "fintech",
        "distribution",
        "finance",
        "healthcare",
        "retail",
        "other",
    ] = Field(description="Industry sector")
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Acme España S.L.", "sector": "saas", "country": "ES"}})


class BudgetComponent(BaseModel):
    """Single component of a budget breakdown."""

    component_id: str = Field(min_length=1, description="Unique component identifier")
    name: str = Field(min_length=1, description="Component name")
    description: str = Field(min_length=1, description="Component description")
    tech_stack: list[str] = Field(default_factory=list, description="Technologies used in this component")
    estimated_hours: int = Field(ge=1, description="Estimated effort in hours")
    complexity: Literal["low", "medium", "high"] = Field(description="Complexity level")
    dependencies: list[str] = Field(default_factory=list, description="List of dependent component IDs")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "component_id": "DISC-001",
                "name": "Discovery phase",
                "description": "Requirements gathering and analysis",
                "tech_stack": ["nodejs", "react"],
                "estimated_hours": 40,
                "complexity": "medium",
                "dependencies": [],
            }
        }
    )


class Budget(BaseModel):
    """Complete budget document with all components and metadata."""

    budget_id: str = Field(min_length=1, description="Unique budget identifier")
    client_metadata: ClientMetadata = Field(description="Client information")
    project_summary: str = Field(min_length=1, description="Project overview")
    main_technology: str = Field(min_length=1, description="Primary technology stack")
    year: int = Field(ge=2000, le=2100, description="Budget year")
    total_estimated_hours: int = Field(ge=1, description="Total project hours")
    components: list[BudgetComponent] = Field(min_length=1, description="List of project components")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "budget_id": "BUD-2024-001",
                "client_metadata": {"name": "Acme España S.L.", "sector": "saas", "country": "ES"},
                "project_summary": "B2B SaaS platform with Workday integration",
                "main_technology": "nodejs",
                "year": 2024,
                "total_estimated_hours": 320,
                "components": [
                    {
                        "component_id": "DISC-001",
                        "name": "Discovery phase",
                        "description": "Requirements gathering and analysis",
                        "tech_stack": ["nodejs", "react"],
                        "estimated_hours": 40,
                        "complexity": "medium",
                        "dependencies": [],
                    }
                ],
            }
        }
    )


# ============================================================================
# Embedding/Chunking Schemas
# ============================================================================


class Chunk(BaseModel):
    """Text chunk ready for embedding."""

    chunk_id: str = Field(min_length=1, description="Unique chunk identifier")
    text: str = Field(min_length=1, description="Chunk text content")
    metadata: dict = Field(default_factory=dict, description="Filterable metadata (e.g. budget_id, component_id, source)")
    token_count: int = Field(ge=0, description="Number of tokens in this chunk")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "chunk_BUD-2024-001_001",
                "text": "B2B SaaS platform integration...",
                "metadata": {"budget_id": "BUD-2024-001", "component_id": "DISC-001", "source": "Budget"},
                "token_count": 45,
            }
        }
    )


class EmbeddedChunk(Chunk):
    """Chunk with precomputed embedding vector."""

    embedding: list[float] = Field(description="Embedding vector (float array)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "chunk_BUD-2024-001_001",
                "text": "B2B SaaS platform integration...",
                "metadata": {"budget_id": "BUD-2024-001", "component_id": "DISC-001"},
                "token_count": 45,
                "embedding": [0.001, -0.005, 0.023, "..."],
            }
        }
    )


# ============================================================================
# Request/Response Schemas
# ============================================================================


class IngestRequest(BaseModel):
    """Request payload for ingest endpoint."""

    budgets: list[Budget] = Field(min_length=1, description="List of budgets to ingest")

    model_config = ConfigDict(json_schema_extra={"example": {"budgets": []}})


class IngestStats(BaseModel):
    """Statistics about the ingestion result."""

    total_budgets: int = Field(ge=0, description="Number of budgets processed")
    total_chunks: int = Field(ge=0, description="Total chunks generated")
    total_tokens: int = Field(ge=0, description="Total tokens across all chunks")
    estimated_cost_usd: float = Field(ge=0.0, description="Estimated USD cost for embedding")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_budgets": 1,
                "total_chunks": 8,
                "total_tokens": 1024,
                "estimated_cost_usd": 0.00512,
            }
        }
    )


class IngestResponse(BaseModel):
    """Response payload from ingest endpoint."""

    chunks: list[EmbeddedChunk] = Field(description="Ingested and embedded chunks")
    stats: IngestStats = Field(description="Processing statistics")

    model_config = ConfigDict(json_schema_extra={"example": {"chunks": [], "stats": {}}})


class RetrievalHit(BaseModel):
    """A retrieved chunk with similarity score for downstream generation."""

    chunk: EmbeddedChunk = Field(description="Chunk returned by retrieval")
    similarity: float = Field(ge=0.0, le=1.0, description="Cosine similarity score")


__all__ = [
    "Budget",
    "BudgetComponent",
    "Chunk",
    "ChunkItem",
    "ChunkRequest",
    "ChunkResponse",
    "ClientMetadata",
    "EmbeddedChunk",
    "EmbedRequest",
    "EmbedResponse",
    "EmbeddingItem",
    "IngestRequest",
    "IngestResponse",
    "IngestStats",
    "RetrievalHit",
]