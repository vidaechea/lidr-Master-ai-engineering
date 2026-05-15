from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.dependencies import DbDep, CurrentUser
from app.schemas.estimation import (
    AsyncEstimationOut,
    EstimationCreate,
    EstimationListItem,
    EstimationOut,
)
from app.services import estimation_service

router = APIRouter(prefix="/estimations", tags=["estimations"])


@router.get("", response_model=list[EstimationListItem])
async def list_estimations(
    current_user: CurrentUser,
    db: DbDep,
    project_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    return await estimation_service.list_estimations(
        db, current_user.id, project_id, status_filter, limit, offset
    )


@router.post("", response_model=EstimationOut, status_code=status.HTTP_201_CREATED)
async def create_estimation(body: EstimationCreate, current_user: CurrentUser, db: DbDep):
    """Synchronous estimation — waits for the AI Engine to complete."""
    return await estimation_service.create_and_run_sync(db, current_user.id, body)


@router.post("/async", response_model=AsyncEstimationOut, status_code=status.HTTP_202_ACCEPTED)
async def create_estimation_async(
    body: EstimationCreate, current_user: CurrentUser, db: DbDep, request: Request
):
    """Async estimation via Redis queue — returns immediately with a job_id."""
    base_url = str(request.base_url).rstrip("/")
    estimation, job_id = await estimation_service.create_async(
        db, current_user.id, body, base_url
    )
    return AsyncEstimationOut(
        estimation_id=estimation.id,
        job_id=job_id,
        status=estimation.status,
    )


@router.get("/{estimation_id}", response_model=EstimationOut)
async def get_estimation(estimation_id: uuid.UUID, current_user: CurrentUser, db: DbDep):
    estimation = await estimation_service.get_estimation(db, estimation_id, current_user.id)
    if not estimation:
        raise HTTPException(status_code=404, detail="Estimation not found")
    return estimation


@router.get("/{estimation_id}/status")
async def get_estimation_status(estimation_id: uuid.UUID, current_user: CurrentUser, db: DbDep):
    """Lightweight polling endpoint for async estimations."""
    estimation = await estimation_service.get_estimation(db, estimation_id, current_user.id)
    if not estimation:
        raise HTTPException(status_code=404, detail="Estimation not found")
    return {
        "id": estimation.id,
        "status": estimation.status,
        "completed_at": estimation.completed_at,
    }
