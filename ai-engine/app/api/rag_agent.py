from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies import (
    enforce_rag_pipeline_estimate_security,
    get_semantic_retriever,
)
from app.domain.agent_estimation import agent_estimate_task_hours, agent_propose_structure
from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.schemas import (
    AgentHoursRequest,
    AgentStructureRequest,
    GenerateStageResponse,
    TaskHoursResult,
)

router = APIRouter(prefix="/rag/agent", tags=["rag-agent"])


@router.post("/structure")
async def propose_structure(
    payload: AgentStructureRequest,
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GenerateStageResponse:
    """Session 12 phase 1: propose module/task structure for human review."""
    return await agent_propose_structure(
        payload.query,
        model=payload.model,
        reasoning_effort=payload.reasoning_effort,
        persona=payload.persona,
    )


@router.post("/hours")
async def estimate_hours(
    payload: AgentHoursRequest,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> TaskHoursResult:
    """Session 12 phase 2: deterministic task-hours with agent-compatible response."""
    top_k = payload.search_top_k or settings.rag_pipeline_task_hours_top_k
    distance_threshold = (
        payload.search_distance_threshold
        if payload.search_distance_threshold is not None
        else settings.rag_pipeline_task_hours_distance_threshold
    )
    return await agent_estimate_task_hours(
        payload.modules,
        retriever=retriever,
        top_k=top_k,
        distance_threshold=distance_threshold,
        contradiction_threshold=settings.rag_pipeline_task_hours_contradiction_threshold,
        model=payload.model,
        reasoning_effort=payload.reasoning_effort,
        max_iterations=payload.max_iterations,
        persona=payload.persona,
    )
