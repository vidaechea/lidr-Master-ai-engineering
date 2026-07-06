"""Router for RAG pipeline estimation endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbDep
from app.schemas.rag_estimation import (
    FullRagEstimationOut,
    HallucinationReportOut,
    RagIndexJobOut,
    RagIndexRunRequest,
    RagIndexRunResponse,
    RagIndexStatsOut,
    RagEstimationListItem,
    RagEstimationRequest,
    RagTaskHoursRequest,
    RagVerifyRequest,
    TaskHoursResultOut,
)
from app.services.rag_estimation_service import RagEstimationService

router = APIRouter(prefix="/rag", tags=["rag-estimations"])
_rag_service = RagEstimationService()


@router.post("/estimate", response_model=FullRagEstimationOut, status_code=status.HTTP_200_OK)
async def create_rag_estimation(
    payload: RagEstimationRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> dict:
    """Create a new RAG pipeline estimation.

    Full orchestration: transcript → reformulation → retrieval → assembly → generation.
    """
    try:
        result = await _rag_service.estimate_from_transcript(
            db,
            current_user.id,
            payload.transcript,
            project_id=None,
            top_k=payload.top_k,
            distance_threshold=payload.distance_threshold,
            idempotency_key=payload.idempotency_key,
        )
        await db.commit()
        return result
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG estimation failed: {str(e)}",
        ) from e


@router.get("/estimates", response_model=list[RagEstimationListItem])
async def list_rag_estimations(
    current_user: CurrentUser,
    db: DbDep,
    project_id: Annotated[Optional[str], Query()] = None,
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    """List RAG estimations for the current user."""
    project_uuid = None
    if project_id:
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project_id")

    estimations = await _rag_service.list_estimations(
        db,
        current_user.id,
        project_id=project_uuid,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    return [
        RagEstimationListItem(
            id=str(est.id),
            transcript=est.transcript[:200],  # Truncate for list view
            summary=est.final_estimate.get("summary", "N/A") if est.final_estimate else "N/A",
            confidence="low" if est.low_confidence else "high",
            modules_count=len(est.final_estimate.get("modules", [])) if est.final_estimate else 0,
            created_at=est.created_at.isoformat(),
            status=est.status,
        ).model_dump()
        for est in estimations
    ]


@router.get("/estimates/{estimation_id}", response_model=FullRagEstimationOut)
async def get_rag_estimation(
    estimation_id: str,
    current_user: CurrentUser,
    db: DbDep,
) -> dict:
    """Retrieve a single RAG estimation by ID."""
    try:
        est_uuid = uuid.UUID(estimation_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid estimation_id")

    estimation = await _rag_service.get_estimation(db, current_user.id, est_uuid)

    if not estimation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimation not found")

    if estimation.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Estimation failed: {estimation.error_detail}",
        )

    if not estimation.pipeline_result:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="Estimation still processing",
        )

    return estimation.pipeline_result


@router.post("/stages/verify", response_model=HallucinationReportOut, status_code=status.HTTP_200_OK)
async def verify_rag_estimation_stage(
    payload: RagVerifyRequest,
    current_user: CurrentUser,
) -> dict:
    """Proxy session 11 semantic verification for grounded RAG line items."""
    _ = current_user
    try:
        return await _rag_service.verify_stage(
            estimate=payload.estimate.model_dump(),
            kept_chunks=[chunk.model_dump() for chunk in payload.kept_chunks],
            use_judge=payload.use_judge,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG verification failed: {str(e)}",
        ) from e


@router.post("/tasks/hours", response_model=TaskHoursResultOut, status_code=status.HTTP_200_OK)
async def estimate_rag_task_hours(
    payload: RagTaskHoursRequest,
    current_user: CurrentUser,
) -> dict:
    """Proxy session 11 task-hours estimation from historical matches."""
    _ = current_user
    try:
        return await _rag_service.estimate_task_hours(
            modules=[module.model_dump() for module in payload.modules],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Task hours estimation failed: {str(e)}",
        ) from e


@router.post("/index/runs", response_model=RagIndexRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_rag_index_run(
    payload: RagIndexRunRequest,
    current_user: CurrentUser,
) -> dict:
    """Proxy session 11 corpus expansion run creation."""
    _ = current_user
    try:
        return await _rag_service.create_index_run(
            documents=payload.documents,
            document_type=payload.document_type,
            chunk_type=payload.chunk_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Index run creation failed: {str(e)}",
        ) from e


@router.get("/index/jobs/{job_id}", response_model=RagIndexJobOut, status_code=status.HTTP_200_OK)
async def get_rag_index_job(
    job_id: str,
    current_user: CurrentUser,
) -> dict:
    """Proxy corpus index job polling endpoint."""
    _ = current_user
    try:
        return await _rag_service.get_index_job(job_id=job_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Index job retrieval failed: {str(e)}",
        ) from e


@router.get("/index/stats", response_model=RagIndexStatsOut, status_code=status.HTTP_200_OK)
async def get_rag_index_stats(
    current_user: CurrentUser,
) -> dict:
    """Proxy corpus index aggregate stats."""
    _ = current_user
    try:
        return await _rag_service.get_index_stats()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Index stats retrieval failed: {str(e)}",
        ) from e
