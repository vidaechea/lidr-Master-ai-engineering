from __future__ import annotations

from typing import Any
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import MODEL_REGISTRY
from app.dependencies import get_runtime_config
from app.foundation.llm.litellm_service import create_litellm_router_service
from app.foundation.llm.runtime_config import (
    MODEL_KEYS,
    RuntimeConfigUnavailable,
    RuntimeModelConfig,
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


async def _runtime_status_payload(runtime_config: RuntimeModelConfig) -> dict[str, Any]:
    snapshot = await runtime_config.snapshot()

    def _entry(key: str) -> dict[str, Any]:
        model_state = snapshot[key]
        return {
            "effective_model": model_state.effective,
            "default_model": model_state.default,
            "overridden": model_state.overridden,
        }

    return {
        "llm_routing": {
            "primary": _entry("LLM_MODEL"),
            "fallback": _entry("LLM_FALLBACK"),
        },
        "acb": {
            "critic": _entry("CRITIC_MODEL"),
        },
        "chunking": {
            "propositional": _entry("PROPOSITIONAL_CHUNKER_MODEL"),
            "contextual_retrieval": _entry("CONTEXTUAL_CHUNKER_MODEL"),
        },
        "conversation": {
            "metadata_extractor": {
                **_entry("METADATA_EXTRACTOR_MODEL"),
                "mode": "heuristic_only",
                "runtime_model_applied": False,
            },
            "compression": {
                **_entry("COMPRESSION_MODEL"),
                "mode": "summarizer_heuristic",
                "runtime_model_applied": False,
            },
        },
        "supported_runtime_keys": list(MODEL_KEYS),
    }


@router.get("/models")
async def get_runtime_models(
    runtime_config: Annotated[RuntimeModelConfig, Depends(get_runtime_config)],
) -> dict[str, Any]:
    available_models = runtime_config.available_models()
    snapshot = await runtime_config.snapshot()
    return _snapshot_payload(snapshot, available_models)


@router.get("/runtime-status")
async def get_runtime_status(
    runtime_config: Annotated[RuntimeModelConfig, Depends(get_runtime_config)],
) -> dict[str, Any]:
    """Runtime diagnostics for model overrides and current component behavior."""
    return await _runtime_status_payload(runtime_config)


@router.put(
    "/models",
    responses={
        400: {"description": "Model exists but required provider key is missing"},
        422: {"description": "Unknown model key or unknown model name"},
        503: {"description": "Runtime config store unavailable"},
    },
)
async def update_runtime_models(
    body: RuntimeModelsUpdateRequest,
    runtime_config: Annotated[RuntimeModelConfig, Depends(get_runtime_config)],
) -> dict[str, Any]:
    available_models = runtime_config.available_models()
    _assert_valid_update(body.models, available_models)

    try:
        await runtime_config.set_overrides(body.models)
    except RuntimeConfigUnavailable as exc:
        log.error("runtime_model_overrides_write_failed", error=str(exc)[:200])
        raise HTTPException(status_code=503, detail="Runtime model config unavailable") from exc

    snapshot = await runtime_config.snapshot()
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
