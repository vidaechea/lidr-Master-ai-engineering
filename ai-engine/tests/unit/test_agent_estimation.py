from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.domain.agent_estimation as agent_estimation
from app.generation.rag.schemas import (
    EstimationQuery,
    RetrievalResult,
    RetrievedChunk,
    TaskHoursEstimate,
    TaskHoursModuleInput,
    TaskHoursResult,
    TaskHoursTaskInput,
)


def _modules() -> list[TaskHoursModuleInput]:
    return [
        TaskHoursModuleInput(
            name="Auth",
            tasks=[TaskHoursTaskInput(name="OAuth backend")],
        )
    ]


@pytest.mark.asyncio
async def test_agent_structure_fallback_decomposes_transcript_into_focused_modules():
    query = EstimationQuery(
        search_text=(
            "Discovery call for a finance platform. We need a backend API, "
            "ERP integration, mobile app, frontend web dashboard, QA testing, "
            "authentication, and deployment automation."
        ),
        sector=None,
        year_from=None,
        year_to=None,
        chunk_types=["budget_component"],
        keywords=[],
    )
    llm_service = SimpleNamespace(
        complete_structured=AsyncMock(side_effect=RuntimeError("provider unavailable"))
    )

    result = await agent_estimation.agent_propose_structure(
        query,
        model="gpt-5",
        reasoning_effort="medium",
        persona=None,
        llm_service=llm_service,
    )

    module_names = [module.name for module in result.estimate.modules]

    assert "Backend API" in module_names
    assert "Frontend Web" in module_names
    assert "Mobile App" in module_names
    assert "ERP Integration" in module_names
    assert "Authentication and Security" in module_names
    assert "QA and Testing" in module_names
    assert "Data Pipeline" not in module_names
    assert all(not module.name.startswith("Discovery call for a finance platform") for module in result.estimate.modules)
    assert all(module.tasks[0].name != "Task 1" for module in result.estimate.modules)
    assert result.agent_trace is not None
    assert result.agent_trace.steps[0].tool_args["source"] == "fallback"


@pytest.mark.asyncio
async def test_agent_hours_recovers_flagged_task(monkeypatch):
    async def fake_estimate_all(**kwargs) -> TaskHoursResult:
        return TaskHoursResult(
            tasks=[TaskHoursEstimate(module="Auth", task="OAuth backend", has_match=False)]
        )

    monkeypatch.setattr(agent_estimation, "estimate_all", fake_estimate_all)

    retriever = SimpleNamespace()
    retriever.search_with_query = AsyncMock(
        return_value=RetrievalResult(
            query="Auth OAuth backend",
            top_k=5,
            candidates_evaluated=1,
            low_confidence=False,
            chunks=[
                RetrievedChunk(
                    source_id="src-1",
                    chunk_id=1,
                    document_id=1,
                    chunk_type="budget_component",
                    content="Component: OAuth backend\nEstimated hours: 48",
                    distance=0.1,
                    metadata={"budget_id": "BUD-1", "estimated_hours": 48},
                )
            ],
        )
    )

    result = await agent_estimation.agent_estimate_task_hours(
        _modules(),
        retriever=retriever,
        top_k=5,
        distance_threshold=0.35,
        contradiction_threshold=0.35,
        model="gpt-5",
        reasoning_effort="medium",
        max_iterations=2,
        persona="be conservative",
    )

    assert result.tasks[0].has_match is True
    assert result.tasks[0].estimated_hours is not None
    assert result.agent_trace is not None
    assert len(result.agent_trace.steps) >= 2
    assert result.agent_trace.steps[0].tool == "search_budgets"


@pytest.mark.asyncio
async def test_agent_hours_skips_recovery_when_all_tasks_grounded(monkeypatch):
    async def fake_estimate_all(**kwargs) -> TaskHoursResult:
        return TaskHoursResult(
            tasks=[
                TaskHoursEstimate(
                    module="Auth",
                    task="OAuth backend",
                    estimated_hours=40,
                    reliability=0.9,
                    has_match=True,
                )
            ]
        )

    monkeypatch.setattr(agent_estimation, "estimate_all", fake_estimate_all)

    retriever = SimpleNamespace()
    retriever.search_with_query = AsyncMock()

    result = await agent_estimation.agent_estimate_task_hours(
        _modules(),
        retriever=retriever,
        top_k=5,
        distance_threshold=0.35,
        contradiction_threshold=0.35,
        model="gpt-5",
        reasoning_effort="medium",
        max_iterations=2,
        persona=None,
    )

    assert result.tasks[0].estimated_hours == 40
    assert result.agent_trace is not None
    assert result.agent_trace.steps == []
    retriever.search_with_query.assert_not_called()
