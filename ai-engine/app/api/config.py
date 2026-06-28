from __future__ import annotations

from typing import Any
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import MODEL_REGISTRY, settings
from app.dependencies import get_runtime_config, get_runtime_retrieval_config
from app.foundation.llm.litellm_service import create_litellm_router_service
from app.foundation.llm.runtime_config import (
    MODEL_KEYS,
    RuntimeConfigUnavailable,
    RuntimeModelConfig,
    RuntimeRetrievalConfig,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


class RuntimeModelsUpdateRequest(BaseModel):
    models: dict[str, str | None] = Field(default_factory=dict)


class RuntimeRetrievalUpdateRequest(BaseModel):
    """Partial update of retrieval runtime toggles.

    Only keys present in the payload are touched.
    - null resets to .env default
    - missing key leaves current runtime value unchanged
    """

    search_mode: str | None = Field(default=None, description="'vector' or 'hybrid'.")
    rerank: bool | None = Field(default=None, description="Enable/disable cross-encoder reranking.")


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


@router.get("/retrieval")
async def get_runtime_retrieval(
    runtime_retrieval: Annotated[RuntimeRetrievalConfig, Depends(get_runtime_retrieval_config)],
) -> dict[str, Any]:
    snapshot = await runtime_retrieval.snapshot()
    return {
        "retrieval": {
            key: {
                "effective": value.effective,
                "default": value.default,
                "overridden": value.overridden,
            }
            for key, value in snapshot.items()
        },
        "reranker_model": settings.rag_pipeline_reranker_model,
    }


@router.put(
    "/retrieval",
    responses={
        422: {"description": "Unknown retrieval mode"},
        503: {"description": "Runtime config store unavailable"},
    },
)
async def update_runtime_retrieval(
    body: RuntimeRetrievalUpdateRequest,
    runtime_retrieval: Annotated[RuntimeRetrievalConfig, Depends(get_runtime_retrieval_config)],
) -> dict[str, Any]:
    sent = body.model_fields_set
    try:
        if "search_mode" in sent:
            try:
                await runtime_retrieval.set_search_mode(body.search_mode)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            log.info("runtime_retrieval_changed", key="search_mode", new_value=body.search_mode)

        if "rerank" in sent:
            await runtime_retrieval.set_rerank(body.rerank)
            log.info("runtime_retrieval_changed", key="rerank", new_value=body.rerank)

    except RuntimeConfigUnavailable as exc:
        log.error("runtime_retrieval_write_failed", error=str(exc)[:200])
        raise HTTPException(status_code=503, detail="Runtime retrieval config unavailable") from exc

    snapshot = await runtime_retrieval.snapshot()
    return {
        "retrieval": {
            key: {
                "effective": value.effective,
                "default": value.default,
                "overridden": value.overridden,
            }
            for key, value in snapshot.items()
        },
        "reranker_model": settings.rag_pipeline_reranker_model,
    }


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
