from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.config import LLMModel


class ExampleFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    NARRATIVE = "narrative"


class ExampleItem(BaseModel):
    title: str
    meeting_summary: str
    estimation_markdown: str


class EstimationRequest(BaseModel):
    transcription: str = Field(
        ...,
        min_length=50,
        description="Meeting transcription text to estimate",
    )
    evaluate: bool = Field(
        default=True,
        description="Run the structural evaluation on the generated estimation",
    )
    model: LLMModel | None = Field(
        default=None,
        description="Override the default model for this request",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (non-reasoning models only)",
    )
    top_p: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling probability (mutually exclusive with temperature)",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Top-K sampling (Anthropic only)",
    )
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Reasoning effort budget for o-series and Claude thinking models",
    )
    max_output_tokens: int = Field(
        default=2_048,
        ge=256,
        le=32_768,
        description="Maximum tokens the model may generate",
    )


class StructureCheck(BaseModel):
    """Level-1 structural evaluation of the generated estimation."""

    has_title: bool
    has_breakdown_table: bool
    has_totals_section: bool
    has_team_section: bool
    has_duration_section: bool
    declared_total_hours: int | None
    sum_row_hours: int | None
    hours_match: bool | None
    declared_total_cost: float | None
    sum_row_cost: float | None
    cost_match: bool | None
    finish_reason_ok: bool
    score: float
    issues: list[str]


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: Optional[int]
    turn_cost_usd: float
    total_cost_usd: float
    response_id: str
    estimated_input_tokens: int
    estimated_precall_cost_usd: float
    validation: StructureCheck | None = None