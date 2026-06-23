"""Pydantic schemas for RAG pipeline estimation endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RagEstimateTask(BaseModel):
    """Single task within an estimation module."""

    name: str = Field(..., min_length=1, max_length=255)
    engineer_days: float = Field(..., ge=0)


class RagEstimateModule(BaseModel):
    """Estimation module with tasks."""

    name: str = Field(..., min_length=1, max_length=255)
    engineer_days: float = Field(..., ge=0)
    tasks: list[RagEstimateTask]


class RagPipelineEstimateOut(BaseModel):
    """RAG pipeline generated estimate (output only)."""

    summary: str
    estimate_markdown: Optional[str] = None
    low_confidence: bool
    modules: list[RagEstimateModule]
    assumptions: list[str]
    sources: list[str]


class GenerationStageOut(BaseModel):
    """Generation stage output wrapper."""

    estimate: RagPipelineEstimateOut


class ReformulationQueryOut(BaseModel):
    """Structured query extracted during reformulation."""

    search_text: str
    sector: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    chunk_types: list[str]
    keywords: list[str]


class ReformulationStageOut(BaseModel):
    """Reformulation stage output."""

    query: ReformulationQueryOut
    used_fallback: bool


class RetrievedChunkOut(BaseModel):
    """Retrieved chunk from semantic search."""

    source_id: str
    chunk_id: int
    document_id: int
    chunk_type: str
    content: str
    distance: float
    metadata: dict


class RetrievalResultOut(BaseModel):
    """Retrieval stage output."""

    query: str
    top_k: int
    candidates_evaluated: int
    low_confidence: bool
    chunks: list[RetrievedChunkOut]


class RetrievalStageOut(BaseModel):
    """Retrieval stage output wrapper."""

    retrieval: RetrievalResultOut


class AssemblyResultOut(BaseModel):
    """Assembly stage output."""

    context_block: str
    included_source_ids: list[str]
    token_count_estimate: int
    truncated: bool


class FullRagEstimationOut(BaseModel):
    """Full RAG pipeline estimation response."""

    request_id: Optional[str] = None
    reformulation: ReformulationStageOut
    retrieval: RetrievalStageOut
    assembly: AssemblyResultOut
    generation: GenerationStageOut
    idempotency_hit: bool = False
    processing_time_ms: Optional[int] = None


class RagEstimationRequest(BaseModel):
    """Request for RAG pipeline estimation."""

    transcript: str = Field(..., min_length=20, max_length=50_000)
    top_k: Optional[int] = Field(None, ge=1, le=50)
    distance_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    idempotency_key: Optional[str] = None


class RagEstimationListItem(BaseModel):
    """Estimation list item for RAG pipeline results."""

    id: str
    transcript: str
    summary: str
    confidence: str  # "high" | "low"
    modules_count: int
    created_at: str
    status: str  # "completed" | "failed"
