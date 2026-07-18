from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphEstimateRequest(BaseModel):
    """Payload to start a graph-driven estimation run."""

    transcript: str = Field(min_length=20, max_length=50_000)
    estimation_id: str | None = Field(default=None, max_length=128)


class GraphResumeRequest(BaseModel):
    """Payload to resume a paused human gate."""

    decision: dict[str, Any] = Field(default_factory=dict)


class PendingGate(BaseModel):
    """Current human gate and artifacts to review."""

    gate: Literal["structure_review", "final_review"]
    estimation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class GraphRunState(BaseModel):
    """Current snapshot for one graph estimation run."""

    estimation_id: str
    state: Literal["paused", "completed", "running"]
    pending_gate: PendingGate | None = None
    complexity: str | None = None
    structure: dict[str, Any] | None = None
    task_hours: list[dict[str, Any]] = Field(default_factory=list)
    estimate: dict[str, Any] | None = None
    analysis_report: dict[str, Any] | None = None
    proposal: str | None = None
    status: Literal["validated", "needs_review"] | None = None
    errors: list[str] = Field(default_factory=list)


class ActivityEntry(BaseModel):
    """One line in the didactic live feed."""

    seq: int = Field(ge=0)
    node: str
    label: str
    message: str
    ts: str


class GraphProgress(GraphRunState):
    """Run snapshot enriched with live activity feed."""

    state: Literal["running", "paused", "completed"]
    activity: list[ActivityEntry] = Field(default_factory=list)


class GraphProposalResponse(BaseModel):
    """Commercial proposal generated from a completed run."""

    estimation_id: str
    title: str
    body_markdown: str
