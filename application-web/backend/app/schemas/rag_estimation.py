"""Pydantic schemas for RAG pipeline estimation endpoints."""

from __future__ import annotations

from typing import Any, Optional

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


class RagSourceReference(BaseModel):
    """Source evidence attached to one grounded line item."""

    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    evidence: str = Field(..., min_length=1)


class RagEstimateLineItem(BaseModel):
    """Line-item estimate with explicit grounding metadata."""

    component: str = Field(..., min_length=1)
    hours: float = Field(..., ge=0)
    rationale: str = Field(..., min_length=1)
    grounded: bool
    sources: list[RagSourceReference] = Field(default_factory=list)


class RagPipelineEstimateOut(BaseModel):
    """RAG pipeline generated estimate (output only)."""

    summary: str
    estimate_markdown: Optional[str] = None
    low_confidence: bool
    modules: list[RagEstimateModule]
    line_items: list[RagEstimateLineItem] = Field(default_factory=list)
    assumptions: list[str]
    sources: list[str]


class HallucinationLineReportOut(BaseModel):
    """Semantic verification status for one estimate line item."""

    component: str
    status: str
    estimated_hours: Optional[float] = None
    anchored_hours: list[float] = Field(default_factory=list)
    cited_chunk_ids: list[str] = Field(default_factory=list)
    reason: str


class HallucinationReportOut(BaseModel):
    """Aggregate semantic verification report."""

    total_lines: int
    grounded_lines: int
    degraded_lines: int
    insufficient_lines: int
    lines: list[HallucinationLineReportOut] = Field(default_factory=list)


class HourRangeOut(BaseModel):
    """Review range when historical matches disagree."""

    min_hours: int
    max_hours: int
    reason: str


class TaskNeighborOut(BaseModel):
    """Historical component used as task-hours evidence."""

    source_id: str
    budget_id: Optional[str] = None
    estimated_hours: int
    distance: float


class TaskHoursEstimateOut(BaseModel):
    """Per-task historical hours estimate."""

    module: str
    task: str
    estimated_hours: Optional[int] = None
    reliability: Optional[float] = None
    has_match: bool
    dispersion: Optional[float] = None
    neighbors: list[TaskNeighborOut] = Field(default_factory=list)
    hours_range: Optional[HourRangeOut] = None


class TaskHoursResultOut(BaseModel):
    """Collection of per-task hours estimates."""

    tasks: list[TaskHoursEstimateOut] = Field(default_factory=list)


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


class RagVerifyRequest(BaseModel):
    """Payload for semantic verification of a staged RAG estimate."""

    estimate: RagPipelineEstimateOut
    kept_chunks: list[RetrievedChunkOut] = Field(default_factory=list)
    use_judge: bool = True


class TaskHoursTaskInput(BaseModel):
    """One task that needs historical-hours estimation."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class TaskHoursModuleInput(BaseModel):
    """One module with tasks for task-hours estimation."""

    name: str = Field(..., min_length=1, max_length=255)
    tasks: list[TaskHoursTaskInput] = Field(default_factory=list)


class RagTaskHoursRequest(BaseModel):
    """Payload for per-task hours estimation."""

    modules: list[TaskHoursModuleInput] = Field(..., min_length=1)


class RagIndexRunRequest(BaseModel):
    """Payload for starting a corpus index expansion run."""

    documents: list[dict[str, Any]] = Field(..., min_length=1)
    document_type: str = Field(default="historical_budget", min_length=1, max_length=50)
    chunk_type: str = Field(default="budget_component", min_length=1, max_length=50)


class RagIndexRunResponse(BaseModel):
    """Accepted corpus index run response."""

    job_id: str
    documents_total: int
    status: str


class RagIndexJobOut(BaseModel):
    """Corpus index job state response."""

    job_id: str
    status: str
    documents_processed: int
    error_message: Optional[str] = None
    started_at: str
    finished_at: Optional[str] = None


class RagCollectionStatsOut(BaseModel):
    """Collection-level corpus stats."""

    collection: str
    documents: int
    chunks: int
    hnsw_indexed: bool


class RagIndexStatsOut(BaseModel):
    """Aggregate corpus index stats response."""

    collections: list[RagCollectionStatsOut] = Field(default_factory=list)
    total_chunks: int


class RagEstimationListItem(BaseModel):
    """Estimation list item for RAG pipeline results."""

    id: str
    transcript: str
    summary: str
    confidence: str  # "high" | "low"
    modules_count: int
    created_at: str
    status: str  # "completed" | "failed"
