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


# ── Callback payload (ai-engine worker → business backend) ────────────────────


class EstimationCallbackPayload(BaseModel):
    job_id: str
    status: Literal["completed", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = None
