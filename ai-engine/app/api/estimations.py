from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.config import settings
from app.dependencies import TierDep
from app.foundation.guardrails.input import InputGuardrailViolation
from app.foundation.prompts.loader import get_examples
from app.domain.schemas.estimation import (
    ActorCriticBossRequest,
    ActorCriticBossResponse,
    EstimationRequest,
    EstimationResponse,
    EstimationResult,
    ExampleItem,
    ExampleFormat,
)
from app.generation.agentic.acb_service import ActorCriticBossService
from app.generation.cag.cache_service import CachedEstimationService
from app.domain.estimation_service import EstimationService
from app.foundation.llm.error_mapper import LLMServiceError

log = structlog.get_logger(__name__)

_INTERNAL_PROCESSING_ERROR_DETAIL = "Internal processing error"

_GUARDRAIL_STATUS: dict[str, int] = {
    "moderation": 400,
    "prompt_injection": 422,
    "pii": 422,
}


def get_estimation_service() -> EstimationService:
    return EstimationService()


def get_cached_estimation_service() -> EstimationService | CachedEstimationService:
    service = EstimationService()
    if settings.cache_enabled:
        return CachedEstimationService(service)
    return service

router = APIRouter(prefix="", tags=["estimations"])

_LLM_ERROR_RESPONSES = {
    400: {"description": "Invalid request parameters"},
    401: {"description": "Invalid or missing API key"},
    404: {"description": "Model not found"},
    413: {"description": "Prompt exceeds model context window"},
    429: {"description": "Rate limit reached or insufficient credit"},
    500: {"description": "Unexpected server error"},
    503: {"description": "Provider unavailable or connection error"},
    504: {"description": "Provider request timed out"},
}


def get_acb_service() -> ActorCriticBossService:
    return ActorCriticBossService()


@router.post("/estimate/acb", responses=_LLM_ERROR_RESPONSES)
async def create_acb_estimation(
    request: ActorCriticBossRequest,
    tier: TierDep,
    prompt_version: Annotated[
        str, Query(description="Prompt template version (e.g. v1, v2)")
    ] = settings.prompt_version,
) -> ActorCriticBossResponse:
    """Actor-Critic-Boss estimation pipeline.

    Runs the candidate estimate through a critic that produces structured
    feedback and a boss that decides to accept, iterate, or synthesize.
    Maximum iterations are capped by *request.max_iterations* (0–3).
    """
    try:
        service = get_acb_service()
        return await service.estimate(request, prompt_version=prompt_version, tier=tier)
    except InputGuardrailViolation as exc:
        raise HTTPException(
            status_code=_GUARDRAIL_STATUS.get(exc.reason, 422),
            detail={"message": exc.message, "reason": exc.reason},
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        log.error("acb_estimation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=_INTERNAL_PROCESSING_ERROR_DETAIL)


@router.get("/examples", response_model=list[ExampleItem])
def get_examples_endpoint(
    tier: Annotated[str, Query(description="User tier: developer | pm | executive")] = "developer",
    version: Annotated[str, Query(description="Prompt template version: v1 | v2")] = "v1",
):
    examples = get_examples(version=version, tier=tier)
    log.debug("examples_requested", tier=tier, version=version, count=len(examples))
    return [
        ExampleItem(title=ex.title, meeting_summary=ex.meeting_summary, estimation_markdown=ex.estimation_markdown)
        for ex in examples
    ]


@router.post("/estimate", responses=_LLM_ERROR_RESPONSES)
async def create_estimation(
    request: EstimationRequest,
    service: Annotated[
        EstimationService | CachedEstimationService,
        Depends(get_cached_estimation_service),
    ],
    tier: TierDep,
    prompt_version: Annotated[str, Query(description="Prompt template version to use (e.g. v1, v2)")] = settings.prompt_version,
) -> EstimationResponse:
    try:
        return await service.estimate(request, prompt_version=prompt_version, tier=tier)
    except InputGuardrailViolation as exc:
        raise HTTPException(
            status_code=_GUARDRAIL_STATUS.get(exc.reason, 422),
            detail={"message": exc.message, "reason": exc.reason},
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        log.error("estimation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=_INTERNAL_PROCESSING_ERROR_DETAIL)


@router.post("/estimate/stream", responses=_LLM_ERROR_RESPONSES)
async def create_estimation_stream(
    request: EstimationRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    tier: TierDep,
    prompt_version: Annotated[str, Query(description="Prompt template version to use (e.g. v1, v2)")] = settings.prompt_version,
) -> StreamingResponse:
    log.info("estimation_stream_requested", transcription_chars=len(request.transcription))

    async def generate():
        try:
            async for delta in service.estimate_stream(request, prompt_version=prompt_version, tier=tier):
                yield delta
        except InputGuardrailViolation as exc:
            raise HTTPException(
                status_code=_GUARDRAIL_STATUS.get(exc.reason, 422),
                detail={"message": exc.message, "reason": exc.reason},
            )
        except LLMServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"X-Prompt-Version": prompt_version},
    )


@router.post("/estimate/structured", responses=_LLM_ERROR_RESPONSES)
async def create_structured_estimation(
    request: EstimationRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    tier: TierDep,
    prompt_version: Annotated[str, Query(description="Prompt template version to use (e.g. v1, v2)")] = settings.prompt_version,
) -> EstimationResponse:
    """Like /estimate but uses instructor + litellm Router to enforce a typed
    EstimationResult (phases, costs, confidence) instead of free-form markdown.

    The response includes the full ``structured_result`` field with the typed
    breakdown, and a rendered markdown ``estimation`` field for display.
    """
    try:
        _, response = await service.estimate_structured(request, prompt_version=prompt_version, tier=tier)
        return response
    except InputGuardrailViolation as exc:
        raise HTTPException(
            status_code=_GUARDRAIL_STATUS.get(exc.reason, 422),
            detail={"message": exc.message, "reason": exc.reason},
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        log.error("structured_estimation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=_INTERNAL_PROCESSING_ERROR_DETAIL)




