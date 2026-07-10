from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.rag_estimation import TaskHoursModuleInput, TaskHoursResultOut


AgentReasoningEffort = Literal["minimal", "low", "medium", "high"]


class AgentProfileConfig(BaseModel):
    model: str | None = None
    reasoning_effort: AgentReasoningEffort | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=20)
    search_top_k: int | None = Field(default=None, ge=1, le=30)
    search_distance_threshold: float | None = Field(default=None, ge=0.0, le=2.0)


class AgentProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    persona: str | None = Field(default=None, max_length=2000)
    config: AgentProfileConfig = Field(default_factory=AgentProfileConfig)
    is_default: bool = False


class AgentProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    persona: str | None = Field(default=None, max_length=2000)
    config: AgentProfileConfig | None = None
    is_default: bool | None = None


class AgentProfileOut(BaseModel):
    id: str
    name: str
    persona: str | None
    config: AgentProfileConfig
    is_default: bool
    created_at: str
    updated_at: str


class EstimationQueryIn(BaseModel):
    search_text: str
    sector: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    chunk_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class AgentTraceStepOut(BaseModel):
    step: int
    reasoning_summary: str | None = None
    tool: str
    tool_args: dict = Field(default_factory=dict)
    observation: str


class AgentTraceOut(BaseModel):
    steps: list[AgentTraceStepOut] = Field(default_factory=list)


class AgentStructureRequest(BaseModel):
    query: EstimationQueryIn
    profile_id: str | None = None


class AgentStructureResponse(BaseModel):
    estimate: dict
    agent_trace: AgentTraceOut | None = None


class AgentHoursRequest(BaseModel):
    modules: list[TaskHoursModuleInput] = Field(min_length=1)
    profile_id: str | None = None


class AgentHoursResponse(TaskHoursResultOut):
    agent_trace: AgentTraceOut | None = None
