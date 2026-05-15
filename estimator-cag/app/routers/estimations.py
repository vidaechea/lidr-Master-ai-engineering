from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.config import settings
from app.guardrails.input import InputGuardrailViolation
from app.prompts.loader import get_examples
from app.schemas.estimation import EstimationRequest, EstimationResponse, EstimationResult, ExampleItem, ExampleFormat
from app.services.estimation_service import EstimationService
from app.services.helpers.error_mapper import LLMServiceError

log = structlog.get_logger(__name__)

_GUARDRAIL_STATUS: dict[str, int] = {
    "moderation": 400,
    "prompt_injection": 422,
    "pii": 422,
}


def get_estimation_service() -> EstimationService:
    return EstimationService()

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


@router.get("/examples", response_model=list[ExampleItem])
def get_examples_endpoint():
    examples = get_examples()
    log.debug("examples_requested", count=len(examples))
    return [
        ExampleItem(title=ex.title, meeting_summary=ex.meeting_summary, estimation_markdown=ex.estimation_markdown)
        for ex in examples
    ]


@router.post("/estimate", responses=_LLM_ERROR_RESPONSES)
async def create_estimation(
    request: EstimationRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    prompt_version: Annotated[str, Query(description="Prompt template version to use (e.g. v1, v2)")] = settings.prompt_version,
) -> EstimationResponse:
    try:
        return await service.estimate(request, prompt_version=prompt_version)
    except InputGuardrailViolation as exc:
        raise HTTPException(
            status_code=_GUARDRAIL_STATUS.get(exc.reason, 422),
            detail={"message": exc.message, "reason": exc.reason},
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        log.error("estimation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/estimate/stream", responses=_LLM_ERROR_RESPONSES)
async def create_estimation_stream(
    request: EstimationRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    prompt_version: Annotated[str, Query(description="Prompt template version to use (e.g. v1, v2)")] = settings.prompt_version,
) -> StreamingResponse:
    log.info("estimation_stream_requested", transcription_chars=len(request.transcription))

    async def generate():
        try:
            async for delta in service.estimate_stream(request, prompt_version=prompt_version):
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
    prompt_version: Annotated[str, Query(description="Prompt template version to use (e.g. v1, v2)")] = settings.prompt_version,
) -> EstimationResponse:
    """Like /estimate but uses instructor + litellm Router to enforce a typed
    EstimationResult (phases, costs, confidence) instead of free-form markdown.

    The response includes the full ``structured_result`` field with the typed
    breakdown, and a rendered markdown ``estimation`` field for display.
    """
    try:
        _, response = await service.estimate_structured(request, prompt_version=prompt_version)
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
        raise HTTPException(status_code=500, detail=str(exc))


