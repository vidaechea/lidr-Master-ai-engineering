from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict


class ComponentSpec(TypedDict):
    name: str
    category: str
    query: str


class GraphTraceEntry(TypedDict):
    reasoning: str
    action: str
    observation: str


class AgentContribution(TypedDict):
    step: int
    agent: str
    action: str
    tool: str | None
    outcome: Literal["ok", "denied", "error"]
    summary: str
    args_digest: str | None
    duration_ms: int | None


class RoutingRecord(TypedDict):
    step: int
    next_agent: str
    reason: str
    source: Literal["llm", "fallback", "limit"]
    decision_confidence: Literal["low", "medium", "high"] | None


def append_routing_history(
    existing: list[RoutingRecord] | None,
    new: list[RoutingRecord] | None,
) -> list[RoutingRecord]:
    merged: dict[int, RoutingRecord] = {}
    for item in list(existing or []) + list(new or []):
        merged[item["step"]] = item
    return [merged[idx] for idx in sorted(merged)]


class EstimationGraphState(TypedDict, total=False):
    estimation_id: str
    transcription: str
    requirements: list[str]
    components: list[ComponentSpec]
    component_hits: dict[str, list[dict[str, object]]]
    budget_hits: Annotated[list[dict[str, object]], operator.add]
    validation_errors: Annotated[list[str], operator.add]
    trace: Annotated[list[GraphTraceEntry], operator.add]
    agent_contributions: Annotated[list[AgentContribution], operator.add]
    supervisor_steps: int
    routing_history: Annotated[list[RoutingRecord], append_routing_history]
    structured_estimate: dict[str, object]
    validation: dict[str, object]
    confidence: float
    status: Literal["validated", "needs_review", "awaiting_human_review"]
    human_decision: dict[str, object]
    final_text: str
