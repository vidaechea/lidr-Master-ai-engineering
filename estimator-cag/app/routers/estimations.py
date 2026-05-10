import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.config import settings
from app.prompts.loader import get_examples, render_estimation_prompt
from app.schemas.estimation import EstimationRequest, EstimationResponse, ExampleItem, ExampleFormat
from app.services.llm.base import BaseLLMService, LLMServiceError
from app.services.helpers.evaluation import evaluate_estimation_structure
from app.services.llm.factory import create_llm_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["estimations"])

def get_llm_service() -> BaseLLMService:
    return create_llm_service()

def _build_estimate_params(request: EstimationRequest) -> dict:
    """Build common parameters for LLM service calls."""
    system_prompt, user_prompt = render_estimation_prompt(request, version=settings.prompt_version)
    return {
        "transcription": request.transcription,
        "model": request.model,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "reasoning_effort": request.reasoning_effort,
        "max_output_tokens": request.max_output_tokens,
        "pre_call": request.pre_call,
        "example_format": request.example_format,
        "num_examples": request.num_examples,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }

def _handle_estimate_error(exc: LLMServiceError, context: str) -> None:
    """Log and raise HTTP exception for LLM service errors."""
    log.warning(
        f"{context}_failed",
        error_type=exc.error_type,
        status_code=exc.status_code,
        detail=exc.message,
    )
    raise HTTPException(status_code=exc.status_code, detail=exc.message)

@router.get("/examples", response_model=list[ExampleItem])
def get_examples_endpoint():
    examples = get_examples()
    log.debug("examples_requested", count=len(examples))
    return [
        ExampleItem(title=ex.title, meeting_summary=ex.meeting_summary, estimation_markdown=ex.estimation_markdown)
        for ex in examples
    ]

@router.post("/estimate")
async def create_estimation(
    request: EstimationRequest,
    service: BaseLLMService = Depends(get_llm_service),
) -> EstimationResponse:
    transcription_length = len(request.transcription)
    log.info("estimation_requested", transcription_chars=transcription_length)
    
    try:
        result = await service.estimate(**_build_estimate_params(request))
    except LLMServiceError as exc:
        _handle_estimate_error(exc, "estimation")
    
    log.info(
        "estimation_completed",
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        turn_cost_usd=result["turn_cost_usd"],
        total_cost_usd=result["total_cost_usd"],
    )
    validation = (
        evaluate_estimation_structure(result["estimation"], result["finish_reason"])
        if request.evaluate
        else None
    )
    return EstimationResponse(**result, validation=validation, prompt_version=settings.prompt_version)


@router.post("/estimate/stream")
async def create_estimation_stream(
    request: EstimationRequest,
    service: BaseLLMService = Depends(get_llm_service),
) -> StreamingResponse:
    transcription_length = len(request.transcription)
    log.info("estimation_stream_requested", transcription_chars=transcription_length)
    
    params = _build_estimate_params(request)

    async def generate():
        try:
            async for delta in service.estimate_stream(**params):
                yield delta
        except LLMServiceError as exc:
            _handle_estimate_error(exc, "estimation_stream")

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"X-Prompt-Version": settings.prompt_version},
    )
