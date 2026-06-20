from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import MODEL_REGISTRY
from app.foundation.llm.litellm_service import create_litellm_router_service
from app.foundation.llm.runtime_config import (
    MODEL_KEYS,
    RuntimeConfigUnavailable,
    runtime_model_config,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


class RuntimeModelsUpdateRequest(BaseModel):
    models: dict[str, str | None] = Field(default_factory=dict)


def _assert_valid_update(changes: dict[str, str | None], available_models: list[str]) -> None:
    available_set = set(available_models)
    for key, value in changes.items():
        if key not in MODEL_KEYS:
            raise HTTPException(status_code=422, detail=f"Unknown model key: {key}")
        if value is None:
            continue
        if value not in MODEL_REGISTRY:
            raise HTTPException(status_code=422, detail=f"Unknown model: {value}")
        if value not in available_set:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{value}' is not available with current provider API keys",
            )


def _snapshot_payload(snapshot: dict[str, Any], available_models: list[str]) -> dict[str, Any]:
    return {
        "models": {
            key: {
                "effective": entry.effective,
                "default": entry.default,
                "overridden": entry.overridden,
            }
            for key, entry in snapshot.items()
        },
        "available_models": available_models,
    }


@router.get("/models")
async def get_runtime_models() -> dict[str, Any]:
    available_models = runtime_model_config.available_models()
    snapshot = await runtime_model_config.snapshot()
    return _snapshot_payload(snapshot, available_models)


@router.put("/models")
async def update_runtime_models(body: RuntimeModelsUpdateRequest) -> dict[str, Any]:
    available_models = runtime_model_config.available_models()
    _assert_valid_update(body.models, available_models)

    try:
        await runtime_model_config.set_overrides(body.models)
    except RuntimeConfigUnavailable as exc:
        log.error("runtime_model_overrides_write_failed", error=str(exc)[:200])
        raise HTTPException(status_code=503, detail="Runtime model config unavailable") from exc

    snapshot = await runtime_model_config.snapshot()
    effective_primary = snapshot["LLM_MODEL"].effective
    effective_fallback = snapshot["LLM_FALLBACK"].effective

    create_litellm_router_service(
        primary_model=effective_primary,
        fallback_model=effective_fallback,
    )

    log.info(
        "runtime_models_updated",
        primary=effective_primary,
        fallback=effective_fallback,
        changed_keys=sorted(body.models.keys()),
    )

    return _snapshot_payload(snapshot, available_models)
