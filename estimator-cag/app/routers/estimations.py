import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.context.examples import ESTIMATION_EXAMPLES
from app.schemas.estimation import EstimationRequest, EstimationResponse, ExampleItem
from app.services.base_llm_service import BaseLLMService, LLMServiceError
from app.services.factory import create_llm_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["estimations"])

def get_llm_service() -> BaseLLMService:
    return create_llm_service()

@router.get("/examples", response_model=list[ExampleItem])
def get_examples():
    log.debug("examples_requested", count=len(ESTIMATION_EXAMPLES))
    return [
        ExampleItem(title=ex.title, meeting_summary=ex.meeting_summary, estimation_markdown=ex.estimation_markdown)
        for ex in ESTIMATION_EXAMPLES
    ]

@router.post("/estimate", response_model=EstimationResponse)
async def create_estimation(
    request: EstimationRequest,
    service: BaseLLMService = Depends(get_llm_service),
) -> EstimationResponse:
    transcription_length = len(request.transcription)
    log.info("estimation_requested", transcription_chars=transcription_length)
    try:
        result = await service.estimate(request.transcription)
    except LLMServiceError as exc:
        log.warning(
            "estimation_failed",
            error_type=exc.type,
            status_code=exc.status_code,
            detail=exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    log.info(
        "estimation_completed",
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        turn_cost_usd=result["turn_cost_usd"],
        total_cost_usd=result["total_cost_usd"],
    )
    return EstimationResponse(
        estimation=result["content"],
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        reasoning_tokens=result["reasoning_tokens"],
        turn_cost_usd=result["turn_cost_usd"],
        total_cost_usd=result["total_cost_usd"],
        response_id=result["response_id"],
        estimated_input_tokens=result["estimated_input_tokens"],
        estimated_precall_cost_usd=result["estimated_precall_cost_usd"],
    )
