from __future__ import annotations

from uuid import uuid4
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.dependencies import enforce_rag_pipeline_estimate_security, get_graph_run_service
from app.domain.schemas.graph_estimation import (
    GraphEstimateRequest,
    GraphProgress,
    GraphProposalResponse,
    GraphResumeRequest,
    GraphRunState,
)
from app.generation.rag.graph_runtime import GraphRunError, GraphRunService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/rag/graph", tags=["rag-graph"])


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


@router.post(
    "/stream",
    response_model=GraphProgress,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_graph_stream(
    payload: GraphEstimateRequest,
    request: Request,
    background: BackgroundTasks,
    service: Annotated[GraphRunService, Depends(get_graph_run_service)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GraphProgress:
    """Start graph flow in background and return initial running state."""
    estimation_id = payload.estimation_id or str(uuid4())
    request_id = _request_id(request)

    background.add_task(
        _safe_start,
        service,
        estimation_id,
        payload.transcript,
        request_id,
    )
    log.info("rag_graph_start_stream", request_id=request_id, estimation_id=estimation_id)
    return GraphProgress(estimation_id=estimation_id, state="running", activity=[])


@router.post(
    "/{estimation_id}/resume-stream",
    response_model=GraphProgress,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_graph_stream(
    estimation_id: str,
    payload: GraphResumeRequest,
    request: Request,
    background: BackgroundTasks,
    service: Annotated[GraphRunService, Depends(get_graph_run_service)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GraphProgress:
    """Resume a paused human gate in background and return running state."""
    request_id = _request_id(request)
    try:
        current = service.get_state(estimation_id=estimation_id)
    except GraphRunError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if current.state != "paused" or current.pending_gate is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending human gate for this estimation_id.",
        )

    background.add_task(
        _safe_resume,
        service,
        estimation_id,
        payload.decision,
        request_id,
    )
    log.info("rag_graph_resume_stream", request_id=request_id, estimation_id=estimation_id)
    return GraphProgress(estimation_id=estimation_id, state="running", activity=service.get_progress(estimation_id=estimation_id)["activity"])


@router.get("/{estimation_id}/state", response_model=GraphRunState)
async def graph_state(
    estimation_id: str,
    service: Annotated[GraphRunService, Depends(get_graph_run_service)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GraphRunState:
    """Get current run snapshot."""
    try:
        return service.get_state(estimation_id=estimation_id)
    except GraphRunError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{estimation_id}/progress", response_model=GraphProgress)
async def graph_progress(
    estimation_id: str,
    service: Annotated[GraphRunService, Depends(get_graph_run_service)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GraphProgress:
    """Get run progress plus activity entries."""
    try:
        data = service.get_progress(estimation_id=estimation_id)
    except GraphRunError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return GraphProgress(**data)


@router.post("/{estimation_id}/proposal", response_model=GraphProposalResponse)
async def graph_proposal(
    estimation_id: str,
    service: Annotated[GraphRunService, Depends(get_graph_run_service)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GraphProposalResponse:
    """Generate or return proposal markdown for completed run."""
    try:
        proposal = service.build_proposal(estimation_id=estimation_id)
    except GraphRunError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return GraphProposalResponse(**proposal)


async def _safe_start(
    service: GraphRunService,
    estimation_id: str,
    transcript: str,
    request_id: str,
) -> None:
    try:
        await service.start(estimation_id=estimation_id, transcript=transcript)
    except Exception as exc:  # noqa: BLE001
        message = f"Graph start failed: {type(exc).__name__}"
        log.error("rag_graph_start_failed", request_id=request_id, estimation_id=estimation_id, error=str(exc)[:300])
        service.record_error(estimation_id=estimation_id, message=message)


async def _safe_resume(
    service: GraphRunService,
    estimation_id: str,
    decision: dict,
    request_id: str,
) -> None:
    try:
        await service.resume(estimation_id=estimation_id, decision=decision)
    except Exception as exc:  # noqa: BLE001
        message = f"Graph resume failed: {type(exc).__name__}"
        log.error("rag_graph_resume_failed", request_id=request_id, estimation_id=estimation_id, error=str(exc)[:300])
        service.record_error(estimation_id=estimation_id, message=message)
