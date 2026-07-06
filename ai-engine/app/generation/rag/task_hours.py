from __future__ import annotations

import asyncio
import statistics

from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.schemas import (
    EstimationQuery,
    HourRange,
    TaskHoursEstimate,
    TaskHoursModuleInput,
    TaskHoursResult,
    TaskHoursTaskInput,
    TaskNeighbor,
)

_WEIGHT_EPSILON = 1e-3


def compose_task_search_text(module: str, task: str, description: str | None) -> str:
    parts = []
    if module:
        parts.append(f"Module: {module}")
    parts.append(f"Task: {task}")
    if description:
        parts.append(description)
    return "\n".join(parts)


def _consensus(neighbors: list[tuple[int, float]]) -> tuple[int, float, float]:
    weights = [1.0 / (_WEIGHT_EPSILON + distance) for _hours, distance in neighbors]
    total_weight = sum(weights)
    hours_values = [hours for hours, _distance in neighbors]
    weighted_hours = sum(weight * hours for weight, (hours, _distance) in zip(weights, neighbors)) / total_weight
    weighted_similarity = (
        sum(weight * max(0.0, 1.0 - distance) for weight, (_hours, distance) in zip(weights, neighbors))
        / total_weight
    )
    mean_hours = statistics.fmean(hours_values)
    dispersion = statistics.pstdev(hours_values) / mean_hours if len(hours_values) > 1 and mean_hours > 0 else 0.0
    reliability = max(0.0, min(1.0, weighted_similarity * (1.0 - min(dispersion, 1.0))))
    return round(weighted_hours), round(reliability, 3), round(dispersion, 3)


def _build_hours_range(neighbors: list[TaskNeighbor], *, threshold: float) -> HourRange | None:
    if len(neighbors) < 2:
        return None
    hours_values = [neighbor.estimated_hours for neighbor in neighbors]
    mean_hours = statistics.fmean(hours_values)
    if mean_hours <= 0:
        return None
    dispersion = statistics.pstdev(hours_values) / mean_hours if len(hours_values) > 1 else 0.0
    if dispersion < threshold:
        return None
    return HourRange(
        min_hours=min(hours_values),
        max_hours=max(hours_values),
        reason="Historical matches disagree materially; review a range instead of a single point.",
    )


async def estimate_one(
    *,
    retriever: SemanticRetriever,
    module: str,
    task: TaskHoursTaskInput,
    top_k: int,
    distance_threshold: float,
    contradiction_threshold: float,
) -> TaskHoursEstimate:
    query = EstimationQuery(
        search_text=compose_task_search_text(module, task.name, task.description),
        sector=None,
        year_from=None,
        year_to=None,
        chunk_types=["budget_component"],
        keywords=[],
    )
    retrieval = await retriever.search_with_query(
        query=query,
        k=top_k,
        distance_threshold=distance_threshold,
    )

    usable_neighbors: list[TaskNeighbor] = []
    for chunk in retrieval.chunks:
        estimated_hours = chunk.metadata.get("estimated_hours")
        if estimated_hours is None or chunk.distance > distance_threshold:
            continue
        try:
            hours_value = int(float(estimated_hours))
        except (TypeError, ValueError):
            continue
        usable_neighbors.append(
            TaskNeighbor(
                source_id=chunk.source_id,
                budget_id=str(chunk.metadata.get("budget_id")) if chunk.metadata.get("budget_id") is not None else None,
                estimated_hours=hours_value,
                distance=chunk.distance,
            )
        )

    if not usable_neighbors:
        return TaskHoursEstimate(module=module, task=task.name, has_match=False)

    estimated_hours_value, reliability, dispersion = _consensus(
        [(neighbor.estimated_hours, neighbor.distance) for neighbor in usable_neighbors]
    )
    return TaskHoursEstimate(
        module=module,
        task=task.name,
        estimated_hours=estimated_hours_value,
        reliability=reliability,
        has_match=True,
        dispersion=dispersion,
        neighbors=usable_neighbors,
        hours_range=_build_hours_range(usable_neighbors, threshold=contradiction_threshold),
    )


async def estimate_all(
    *,
    modules: list[TaskHoursModuleInput],
    retriever: SemanticRetriever,
    top_k: int,
    distance_threshold: float,
    contradiction_threshold: float,
) -> TaskHoursResult:
    tasks = [
        estimate_one(
            retriever=retriever,
            module=module.name,
            task=task,
            top_k=top_k,
            distance_threshold=distance_threshold,
            contradiction_threshold=contradiction_threshold,
        )
        for module in modules
        for task in module.tasks
    ]
    estimates = await asyncio.gather(*tasks)
    return TaskHoursResult(tasks=estimates)