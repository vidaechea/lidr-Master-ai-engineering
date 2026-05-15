from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.estimation import Estimation
from app.schemas.estimation import EstimationCreate
from app.services import ai_client


async def list_estimations(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Estimation]:
    query = select(Estimation).where(Estimation.user_id == user_id)
    if project_id:
        query = query.where(Estimation.project_id == project_id)
    if status:
        query = query.where(Estimation.status == status)
    query = query.order_by(Estimation.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_estimation(
    db: AsyncSession, estimation_id: uuid.UUID, user_id: uuid.UUID
) -> Estimation | None:
    result = await db.execute(
        select(Estimation).where(
            Estimation.id == estimation_id,
            Estimation.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_estimation_by_job(db: AsyncSession, job_id: str) -> Estimation | None:
    """Lookup by job_id stored in request_params JSONB."""
    result = await db.execute(
        select(Estimation).where(
            Estimation.request_params["job_id"].astext == job_id
        )
    )
    return result.scalar_one_or_none()


async def create_and_run_sync(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: EstimationCreate,
) -> Estimation:
    """Create an Estimation record, call the AI Engine synchronously, persist result."""
    # Build the ai-engine payload (exclude backend-only fields)
    ai_payload = data.model_dump(
        exclude={"project_id", "prompt_version"},
    )
    ai_payload["prompt_version"] = data.prompt_version

    # Persist in 'processing' state
    estimation = Estimation(
        user_id=user_id,
        project_id=data.project_id,
        transcription=data.transcription,
        status="processing",
        prompt_version=data.prompt_version,
        request_params=ai_payload,
    )
    db.add(estimation)
    await db.commit()
    await db.refresh(estimation)

    try:
        ai_response = await ai_client.estimate_sync(ai_payload)
        _apply_ai_response(estimation, ai_response)
        estimation.status = "completed"
        estimation.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        estimation.status = "failed"
        estimation.error_detail = str(exc)
        await db.commit()
        raise

    await db.commit()
    await db.refresh(estimation)
    return estimation


async def create_async(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: EstimationCreate,
    backend_base_url: str,
) -> tuple[Estimation, str]:
    """Create an Estimation in 'pending' state and enqueue in the AI Engine worker."""
    ai_payload = data.model_dump(exclude={"project_id"})

    estimation = Estimation(
        user_id=user_id,
        project_id=data.project_id,
        transcription=data.transcription,
        status="pending",
        prompt_version=data.prompt_version,
        request_params=ai_payload,
    )
    db.add(estimation)
    await db.commit()
    await db.refresh(estimation)

    callback_url = f"{backend_base_url}/v1/internal/estimation-callback"
    # Store the estimation id so the callback can find it by job_id
    job_id = await ai_client.enqueue_async(ai_payload, callback_url)

    # Store job_id for status polling
    estimation.request_params = {**ai_payload, "job_id": job_id}
    await db.commit()

    return estimation, job_id


async def apply_callback(
    db: AsyncSession,
    estimation: Estimation,
    status: str,
    result: dict | None,
    error: str | None,
) -> Estimation:
    estimation.status = status
    if status == "completed" and result:
        _apply_ai_response(estimation, result)
        estimation.completed_at = datetime.now(timezone.utc)
    elif status == "failed":
        estimation.error_detail = error
    await db.commit()
    await db.refresh(estimation)
    return estimation


def _apply_ai_response(estimation: Estimation, response: dict) -> None:
    estimation.estimation_markdown = response.get("estimation")
    estimation.model_used = response.get("model")
    estimation.input_tokens = response.get("input_tokens")
    estimation.output_tokens = response.get("output_tokens")
    estimation.turn_cost_usd = response.get("turn_cost_usd")
    estimation.total_cost_usd = response.get("total_cost_usd")
    estimation.requirements = response.get("requirements")
    estimation.validation_result = response.get("validation")
    estimation.structured_result = response.get("structured_result")
    if not estimation.prompt_version:
        estimation.prompt_version = response.get("prompt_version")
