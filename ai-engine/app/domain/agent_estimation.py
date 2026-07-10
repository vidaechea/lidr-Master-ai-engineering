from __future__ import annotations

import re

import structlog

from app.domain.schemas.agent_trace import AgentStep, AgentTrace
from app.generation.rag.schemas import (
    EstimateModule,
    EstimateTask,
    EstimationQuery,
    GenerateStageResponse,
    RagPipelineEstimate,
    TaskHoursEstimate,
    TaskHoursModuleInput,
    TaskHoursTaskInput,
    TaskNeighbor,
    TaskHoursResult,
)
from app.generation.rag.task_hours import compose_task_search_text, distance_weighted_consensus, estimate_all
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)

_LOW_RELIABILITY = 0.35


def _should_recover(estimate: TaskHoursEstimate) -> bool:
    if not estimate.has_match:
        return True
    if estimate.hours_range is not None:
        return True
    if estimate.reliability is not None and estimate.reliability < _LOW_RELIABILITY:
        return True
    return False


def _extract_estimated_hours(content: str, metadata: dict[str, object]) -> int | None:
    raw_value = metadata.get("estimated_hours")
    if raw_value is None:
        match = re.search(r"Estimated hours:\s*(\d+(?:\.\d+)?)", content)
        raw_value = match.group(1) if match else None
    if raw_value is None:
        return None
    try:
        return int(float(raw_value))
    except (TypeError, ValueError):
        return None


def _build_neighbor_list(retrieval_chunks, *, distance_threshold: float) -> list[TaskNeighbor]:
    neighbors: list[TaskNeighbor] = []
    for chunk in retrieval_chunks:
        if chunk.distance > distance_threshold:
            continue
        hours = _extract_estimated_hours(chunk.content, chunk.metadata)
        if hours is None:
            continue
        neighbors.append(
            TaskNeighbor(
                source_id=chunk.source_id,
                budget_id=str(chunk.metadata.get("budget_id")) if chunk.metadata.get("budget_id") is not None else None,
                estimated_hours=hours,
                distance=chunk.distance,
            )
        )
    return neighbors


async def _search_task_neighbors(
    *,
    retriever: SemanticRetriever,
    module: str,
    task: TaskHoursTaskInput,
    top_k: int,
    distance_threshold: float,
):
    query = EstimationQuery(
        search_text=compose_task_search_text(module, task.name, task.description),
        sector=None,
        year_from=None,
        year_to=None,
        chunk_types=["budget_component"],
        keywords=[],
    )
    try:
        return await retriever.search_with_query(
            query=query,
            k=top_k,
            distance_threshold=distance_threshold,
            mode="hybrid",
            rerank=True,
        )
    except RuntimeError as exc:
        message = str(exc)
        if (
            "Reranking requested" not in message
            and "sentence-transformers is required" not in message
        ):
            raise
        return await retriever.search_with_query(
            query=query,
            k=top_k,
            distance_threshold=distance_threshold,
            mode="hybrid",
            rerank=False,
        )


def _find_task_input(modules: list[TaskHoursModuleInput], module_name: str, task_name: str) -> TaskHoursTaskInput | None:
    for module in modules:
        if module.name != module_name:
            continue
        for task in module.tasks:
            if task.name == task_name:
                return task
    return None


def _propose_modules(query: EstimationQuery) -> list[EstimateModule]:
    """Build a lightweight structure from query signals.

    This is a first implementation slice to expose the Session 12 API surface.
    It prefers explicit query keywords, then falls back to search_text.
    """
    labels = [keyword.strip() for keyword in query.keywords if keyword.strip()]
    if not labels:
        labels = [query.search_text.strip()]

    modules: list[EstimateModule] = []
    for index, label in enumerate(labels, start=1):
        task = EstimateTask(
            name=f"Task {index}",
            engineer_days=0.0,
        )
        modules.append(
            EstimateModule(
                name=label[:80],
                engineer_days=0.0,
                tasks=[task],
            )
        )
    return modules


def agent_propose_structure(
    query: EstimationQuery,
    *,
    model: str | None,
    reasoning_effort: str | None,
    persona: str | None,
) -> GenerateStageResponse:
    modules = _propose_modules(query)
    reasoning = (
        "Structure proposed from query keywords for human review."
        if modules
        else "Insufficient context to propose modules."
    )

    estimate = RagPipelineEstimate(
        summary=reasoning,
        estimate_markdown=None,
        low_confidence=not bool(modules),
        modules=modules,
        line_items=[],
        assumptions=[],
        sources=[],
    )

    trace = AgentTrace(
        steps=[
            AgentStep(
                step=1,
                reasoning_summary="Propose an editable module->task tree before task-hours grounding.",
                tool="propose_structure",
                tool_args={
                    "modules": len(modules),
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                    "persona": bool(persona and persona.strip()),
                },
                observation=f"decomposed into {len(modules)} module(s)",
            )
        ]
    )

    return GenerateStageResponse(estimate=estimate, agent_trace=trace)


async def agent_estimate_task_hours(
    modules: list[TaskHoursModuleInput],
    *,
    retriever: SemanticRetriever,
    top_k: int,
    distance_threshold: float,
    contradiction_threshold: float,
    model: str | None,
    reasoning_effort: str | None,
    max_iterations: int | None,
    persona: str | None,
) -> TaskHoursResult:
    base = await estimate_all(
        modules=modules,
        retriever=retriever,
        top_k=top_k,
        distance_threshold=distance_threshold,
        contradiction_threshold=contradiction_threshold,
    )

    flagged = [estimate for estimate in base.tasks if _should_recover(estimate)]
    if not flagged:
        log.info(
            "agent_hours_phase_completed",
            tasks=len(base.tasks),
            flagged=0,
            recovered=0,
            model=model,
            reasoning_effort=reasoning_effort,
            max_iterations=max_iterations,
            persona=bool(persona and persona.strip()),
        )
        return TaskHoursResult(tasks=base.tasks, agent_trace=AgentTrace())

    max_attempts = max(1, min(int(max_iterations or 2), 3))
    step = 1
    trace_steps: list[AgentStep] = []
    recovered_by_key: dict[tuple[str, str], TaskHoursEstimate] = {}

    for estimate in flagged:
        task_input = _find_task_input(modules, estimate.module, estimate.task)
        if task_input is None:
            continue

        neighbors: list[TaskNeighbor] = []
        retrieval_chunks = []
        for attempt in range(max_attempts):
            retrieval = await _search_task_neighbors(
                retriever=retriever,
                module=estimate.module,
                task=task_input,
                top_k=top_k,
                distance_threshold=distance_threshold,
            )
            retrieval_chunks = retrieval.chunks
            neighbors = _build_neighbor_list(retrieval_chunks, distance_threshold=distance_threshold)
            trace_steps.append(
                AgentStep(
                    step=step,
                    reasoning_summary=(
                        f"Recover hours for task {estimate.module}/{estimate.task}; "
                        f"attempt {attempt + 1}/{max_attempts}."
                    ),
                    tool="search_budgets",
                    tool_args={
                        "query": compose_task_search_text(estimate.module, task_input.name, task_input.description),
                        "top_k": top_k,
                        "distance_threshold": distance_threshold,
                    },
                    observation=f"{len(neighbors)} usable analogs from {len(retrieval_chunks)} retrieved chunks",
                )
            )
            step += 1
            if neighbors:
                break

        if not neighbors:
            continue

        estimated_hours, reliability, dispersion = distance_weighted_consensus(
            [(neighbor.estimated_hours, neighbor.distance) for neighbor in neighbors]
        )
        recovered = estimate.model_copy(
            update={
                "estimated_hours": estimated_hours,
                "reliability": reliability,
                "dispersion": dispersion,
                "has_match": True,
                "hours_range": None,
                "neighbors": neighbors,
            }
        )
        recovered_by_key[(estimate.module, estimate.task)] = recovered
        trace_steps.append(
            AgentStep(
                step=step,
                reasoning_summary="Derive deterministic hours from nearest historical analogs.",
                tool="derive_task_hours",
                tool_args={
                    "module": estimate.module,
                    "task": estimate.task,
                    "neighbors": [neighbor.model_dump() for neighbor in neighbors],
                },
                observation=(
                    f"{estimate.module}/{estimate.task}: {estimated_hours}h "
                    f"(reliability {reliability})"
                ),
            )
        )
        step += 1

    merged: list[TaskHoursEstimate] = []
    for estimate in base.tasks:
        merged.append(recovered_by_key.get((estimate.module, estimate.task), estimate))

    log.info(
        "agent_hours_phase_completed",
        tasks=len(base.tasks),
        flagged=len(flagged),
        recovered=len(recovered_by_key),
        model=model,
        reasoning_effort=reasoning_effort,
        max_iterations=max_iterations,
        persona=bool(persona and persona.strip()),
    )

    return TaskHoursResult(tasks=merged, agent_trace=AgentTrace(steps=trace_steps))
