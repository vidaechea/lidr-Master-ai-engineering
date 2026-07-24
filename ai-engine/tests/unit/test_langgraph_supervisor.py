from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.langgraph_flow import SequentialEstimationGraph
from app.agents.schemas import SupervisorRoutingDecision
from app.config import settings


def _flow() -> SequentialEstimationGraph:
    return SequentialEstimationGraph(retriever=MagicMock())


@pytest.mark.asyncio
async def test_supervisor_uses_fallback_when_router_fails():
    flow = _flow()
    flow._route_with_model = AsyncMock(side_effect=RuntimeError("router down"))

    state = {
        "estimation_id": "run-1",
        "transcription": "Need backend and mobile app with ERP integration",
        "routing_history": [],
        "agent_contributions": [],
        "supervisor_steps": 0,
    }

    command = await flow.supervisor(state)

    assert command.goto == "requirements_extractor"
    assert command.update["routing_history"][0]["source"] == "fallback"


@pytest.mark.asyncio
async def test_supervisor_overrides_illegal_destination_with_fallback():
    flow = _flow()
    flow._route_with_model = AsyncMock(
        return_value=SupervisorRoutingDecision(
            next_agent="budget_searcher",
            reason="Search first",
            confidence="high",
        )
    )

    # budget_searcher is illegal before components exist, so fallback must route to requirements_extractor
    state = {
        "estimation_id": "run-2",
        "transcription": "Need backend and mobile app with ERP integration",
        "routing_history": [],
        "agent_contributions": [],
        "supervisor_steps": 0,
    }

    command = await flow.supervisor(state)

    assert command.goto == "requirements_extractor"
    assert command.update["routing_history"][0]["source"] == "fallback"


@pytest.mark.asyncio
async def test_supervisor_honors_step_budget_limit(monkeypatch):
    flow = _flow()
    monkeypatch.setattr(settings, "agentic_supervisor_max_steps", 2)

    state = {
        "estimation_id": "run-3",
        "transcription": "Need backend and mobile app with ERP integration",
        "routing_history": [],
        "agent_contributions": [],
        "supervisor_steps": 2,
    }

    command = await flow.supervisor(state)

    assert command.goto == "finalize"
    assert command.update["routing_history"][0]["source"] == "limit"


@pytest.mark.asyncio
async def test_supervisor_routes_to_human_review_on_finish_with_low_confidence():
    flow = _flow()
    flow._route_with_model = AsyncMock(
        return_value=SupervisorRoutingDecision(
            next_agent="finish",
            reason="All workers complete",
            confidence="high",
        )
    )

    state = {
        "estimation_id": "run-4",
        "transcription": "Need backend and mobile app with ERP integration",
        "requirements": ["backend", "mobile"],
        "components": [
            {"name": "Backend API", "category": "backend", "query": "backend"},
            {"name": "Mobile App", "category": "mobile", "query": "mobile"},
        ],
        "component_hits": {
            "Backend API": [{"amount": 40}],
            "Mobile App": [{"amount": 20}],
        },
        "structured_estimate": {
            "components": [
                {
                    "name": "Backend API",
                    "reference_amounts": [40.0],
                    "estimated_amount": 40.0,
                    "unit": "hours",
                    "reference_count": 1,
                }
            ],
            "total_amount": 40.0,
            "unit": "hours",
            "method": "arithmetic_mean",
            "assumptions": [],
            "status": "needs_review",
            "confidence": 0.2,
            "validation": {"errors": ["low confidence"]},
        },
        "validation": {"errors": ["low confidence"]},
        "confidence": 0.2,
        "routing_history": [],
        "agent_contributions": [],
        "supervisor_steps": 0,
    }

    command = await flow.supervisor(state)

    assert command.goto == "human_review_gate"
