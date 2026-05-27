"""ARQ worker — consumes estimation tasks from Redis and calls back to the business backend."""

from __future__ import annotations

import httpx
import structlog
from arq.connections import RedisSettings

from app.config import settings
from app.schemas.estimation import EstimationRequest
from app.services.estimation_service import EstimationService

log = structlog.get_logger(__name__)


async def estimate_task(
    ctx: dict,
    estimation_request_dict: dict,
    callback_url: str,
    job_id: str,
    prompt_version: str,
) -> None:
    """Process a single estimation and POST the result to ``callback_url``."""
    log.info("worker_estimate_start", job_id=job_id)
    request = EstimationRequest(**estimation_request_dict)
    service: EstimationService = ctx["estimation_service"]

    try:
        response = await service.estimate(request, prompt_version=prompt_version)
        payload = {
            "job_id": job_id,
            "status": "completed",
            "result": response.model_dump(),
        }
    except Exception as exc:
        log.error("worker_estimate_failed", job_id=job_id, error=str(exc))
        payload = {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            await client.post(
                callback_url,
                json=payload,
                headers={"X-Internal-API-Key": settings.internal_api_key or ""},
            )
            log.info("worker_callback_sent", job_id=job_id, callback_url=callback_url)
        except Exception as exc:
            log.error("worker_callback_failed", job_id=job_id, error=str(exc))


def startup(ctx: dict) -> None:
    ctx["estimation_service"] = EstimationService()


async def shutdown(ctx: dict) -> None:
    """Clean up resources on worker shutdown."""
    pass


class WorkerSettings:
    functions = [estimate_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = "arq:estimation"
    max_jobs = 4
    job_timeout = 300  # 5 minutes per estimation task
