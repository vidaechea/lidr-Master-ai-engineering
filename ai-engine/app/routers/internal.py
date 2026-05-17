"""Internal async estimation endpoint consumed by the business backend via Redis/ARQ."""

from __future__ import annotations

import uuid

import arq
import structlog
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.estimation import EstimationRequest

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/estimate/async", status_code=202)
async def enqueue_estimation(
    request: EstimationRequest,
    callback_url: str,
) -> dict:
    """Enqueue an estimation task in Redis.

    Returns ``{job_id}`` immediately; the ARQ worker processes the request and
    POSTs the result back to ``callback_url`` when done.
    """
    job_id = str(uuid.uuid4())
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await arq.create_pool(redis_settings)
    try:
        await pool.enqueue_job(
            "estimate_task",
            request.model_dump(),
            callback_url,
            job_id,
            _job_id=job_id,
        )
    except Exception as exc:
        log.error("enqueue_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Queue unavailable") from exc
    finally:
        await pool.aclose()

    log.info("estimation_enqueued", job_id=job_id, callback_url=callback_url)
    return {"job_id": job_id}
