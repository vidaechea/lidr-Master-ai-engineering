from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchBudgetsDateRange(BaseModel):
    from_year: int | None = Field(default=None, ge=2000, le=2100)
    to_year: int | None = Field(default=None, ge=2000, le=2100)


class SearchBudgetsFilters(BaseModel):
    component_type: str | None = None
    client_sector: str | None = None
    date_range: SearchBudgetsDateRange | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class HistoricalBudgetHit(BaseModel):
    source_id: str
    budget_id: str | None = None
    component_name: str
    amount: float
    unit: str = "hours"
    year: int | None = None
    client_sector: str | None = None
    main_technology: str | None = None
    distance: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class EstimateComponentInput(BaseModel):
    name: str
    reference_amounts: list[float] = Field(default_factory=list)


class EstimatedComponent(BaseModel):
    name: str
    reference_amounts: list[float] = Field(default_factory=list)
    estimated_amount: float
    unit: str = "hours"
    reference_count: int = Field(ge=0)


class AgenticEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: list[EstimatedComponent] = Field(default_factory=list)
    total_amount: float
    unit: str = "hours"
    method: str
    assumptions: list[str] = Field(default_factory=list)
    status: Literal["validated", "needs_review", "awaiting_human_review"] = "needs_review"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    validation: dict[str, object] = Field(default_factory=dict)


class AgentTraceStep(BaseModel):
    step: int = Field(ge=1)
    reasoning: str
    action: str
    observation: str


class AgenticEstimationResponse(BaseModel):
    estimation: str
    structured_result: AgenticEstimate
    trace: list[AgentTraceStep] = Field(default_factory=list)
    model: str
    response_id: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0
    prompt_version: str
    reasoning_effort: Literal["medium"] = "medium"


class AgenticResumeRequest(BaseModel):
    decision: dict[str, object] = Field(default_factory=dict)
