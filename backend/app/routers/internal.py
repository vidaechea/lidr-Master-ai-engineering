"""Internal endpoints — called by the AI Engine worker, not by the Angular SPA."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.dependencies import DbDep
from app.schemas.estimation import EstimationCallbackPayload
from app.services import estimation_service

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])

_CALLBACK_TAG = "X-Internal-API-Key"


def _verify_internal_key(request: Request) -> None:
    secret = settings.internal_api_key
    if secret and request.headers.get(_CALLBACK_TAG) != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/estimation-callback", status_code=200)
async def estimation_callback(
    body: EstimationCallbackPayload,
    request: Request,
    db: DbDep,
):
    _verify_internal_key(request)
    estimation = await estimation_service.get_estimation_by_job(db, body.job_id)
    if not estimation:
        log.warning("callback_unknown_job", job_id=body.job_id)
        raise HTTPException(status_code=404, detail="Estimation not found")

    await estimation_service.apply_callback(
        db,
        estimation,
        status=body.status,
        result=body.result,
        error=body.error,
    )
    log.info("callback_applied", job_id=body.job_id, status=body.status)
    return {"ok": True}
