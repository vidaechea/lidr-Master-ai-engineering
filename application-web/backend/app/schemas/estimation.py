from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Request (mirrors ai-engine EstimationRequest) ─────────────────────────────

OutputFormat = Literal["phases_table", "line_items", "narrative"]
ExampleFormat = Literal["markdown", "json", "narrative"]
DetailLevel = Literal["summary", "medium", "detailed"]
ProjectType = Literal["mobile_app", "web_saas", "internal_tool", "data_pipeline"]


class ReferenceProject(BaseModel):
    name: str
    description: str
    total_hours: int | None = None
    total_cost: int | None = None


class EstimationCreate(BaseModel):
    """What the Angular SPA sends to the Business API."""

    transcription: str = Field(min_length=20)
    project_id: uuid.UUID | None = None

    # AI Engine params — forwarded as-is
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    max_output_tokens: int = Field(default=2048, ge=256, le=32768)
    pre_call: bool = False
    output_format: OutputFormat = "phases_table"
    example_format: ExampleFormat = "markdown"
    num_examples: int = Field(default=3, ge=0, le=5)
    project_type: ProjectType | None = None
    detail_level: DetailLevel | None = None
    prompt_version: str = "v1"
    reference_projects: list[ReferenceProject] | None = None

    # ACB pipeline params — only used when estimation_mode="acb"
    estimation_mode: Literal["standard", "acb"] = "standard"
    acb_max_iterations: int = Field(
        default=2,
        ge=0,
        le=3,
        description="Maximum ACB re-iteration cycles (0–3). Ignored in standard mode.",
    )


# ── Response ──────────────────────────────────────────────────────────────────


class EstimationOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    status: str
    transcription: str
    model_used: str | None
    prompt_version: str | None
    estimation_markdown: str | None
    structured_result: dict[str, Any] | None
    requirements: str | None
    validation_result: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    turn_cost_usd: float | None
    total_cost_usd: float | None
    error_detail: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class EstimationListItem(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    status: str
    model_used: str | None
    total_cost_usd: float | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AsyncEstimationOut(BaseModel):
    estimation_id: uuid.UUID
    job_id: str
    status: str = "pending"


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionMessageOut(BaseModel):
    role: str
    content: str


class SessionProjectMetadataOut(BaseModel):
    project_name: str | None = None
    assumed_team_size: int | None = None
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = None


class SessionStateOut(BaseModel):
    session_id: str
    project_metadata: SessionProjectMetadataOut
    history: list[SessionMessageOut]
    turn_count: int


class SessionEstimationOut(BaseModel):
    estimation: str
    model: str
    response_id: str | None
    input_tokens: int
    output_tokens: int
    turn_cost_usd: float
    total_cost_usd: float
    estimated_input_tokens: int
    estimated_precall_cost_usd: float | None
    requirements: str | None
    pre_call_cost_usd: float | None
    validation: dict[str, Any] | None = None
    prompt_version: str
    structured_result: dict[str, Any] | None = None


class CacheMetricsOut(BaseModel):
    hits: int
    misses: int
    total: int
    hit_rate_pct: float
    cost_avoided_usd: float
    avg_latency_hit_ms: float | None
    avg_latency_miss_ms: float | None
    speedup_x: int | None
    stale_reports: int
    stale_rate_pct: float


class RuntimeModelItem(BaseModel):
    effective: str
    default: str
    overridden: bool


class RuntimeModelsOut(BaseModel):
    models: dict[str, RuntimeModelItem]
    available_models: list[str]


class RuntimeModelsUpdateIn(BaseModel):
    models: dict[str, str | None]


class ChunkingComparisonIn(BaseModel):
    queries: list[str] = Field(default_factory=list)
    strategies: list[str] | None = None
    top_k: int = Field(default=3, ge=1, le=10)


class ChunkingStrategyStatsOut(BaseModel):
    total_chunks: int
    total_tokens: int
    avg_tokens_per_chunk: float
    min_tokens: int
    max_tokens: int
    estimated_cost_usd: float


class ChunkingComparisonHitOut(BaseModel):
    chunk_id: str
    payload: str
    similarity: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkingComparisonQueryOut(BaseModel):
    query: str
    results: list[ChunkingComparisonHitOut] = Field(default_factory=list)


class ChunkingComparisonOut(BaseModel):
    stats_per_strategy: dict[str, ChunkingStrategyStatsOut]
    queries_per_strategy: dict[str, list[ChunkingComparisonQueryOut]]


# ── Callback payload (ai-engine worker → business backend) ────────────────────


class EstimationCallbackPayload(BaseModel):
    job_id: str
    status: Literal["completed", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = None
