import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.context.examples import ESTIMATION_EXAMPLES
from app.schemas.estimation import EstimationRequest, EstimationResponse, ExampleItem, OutputFormat
from app.services.base_llm_service import BaseLLMService, LLMServiceError
from app.services.evaluation import evaluate_estimation_structure
from app.services.factory import create_llm_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["estimations"])

_OUTPUT_FORMAT_INSTRUCTIONS: dict[OutputFormat, str] = {
    OutputFormat.PHASES_TABLE: (
        "Output format: phases table — Organize the estimate as a markdown table "
        "grouped by project phase (e.g., Discovery, Design, Development, Testing, Deployment). "
        "Include a subtotals row per phase and a final totals section."
    ),
    OutputFormat.LINE_ITEMS: (
        "Output format: line items — Produce a single flat markdown table where each row "
        "is one individual feature or task. Do not group by phase. "
        "List each deliverable as its own line item."
    ),
    OutputFormat.NARRATIVE: (
        "Output format: narrative — Write the estimate as flowing prose without tables. "
        "Describe the scope, effort, team composition, and timeline in clear paragraphs."
    ),
    OutputFormat.MARKDOWN: (
        "Output format: markdown — Produce a well-structured markdown estimate with "
        "a breakdown table, totals, team, and timeline sections."
    ),
    OutputFormat.JSON: (
        "Output format: JSON — Return the estimate as a JSON object with fields: "
        "breakdown (array of {task, hours, cost_eur}), total_hours, total_cost_eur, "
        "team (array of strings), duration_weeks (integer). No markdown, only the JSON object."
    ),
}


def _enrich_transcription(request: EstimationRequest) -> str:
    """Prepend structured project context and output format instructions."""
    parts: list[str] = []
    if request.project_type:
        parts.append(f"Project type: {request.project_type.value}")
    if request.detail_level:
        parts.append(f"Detail level: {request.detail_level.value}")
    parts.append(_OUTPUT_FORMAT_INSTRUCTIONS[request.output_format])
    return "\n".join(parts) + "\n\n---\n\n" + request.transcription


def get_llm_service() -> BaseLLMService:
    return create_llm_service()

@router.get("/examples", response_model=list[ExampleItem])
def get_examples():
    log.debug("examples_requested", count=len(ESTIMATION_EXAMPLES))
    return [
        ExampleItem(title=ex.title, meeting_summary=ex.meeting_summary, estimation_markdown=ex.estimation_markdown)
        for ex in ESTIMATION_EXAMPLES
    ]

@router.post("/estimate")
async def create_estimation(
    request: EstimationRequest,
    service: BaseLLMService = Depends(get_llm_service),
) -> EstimationResponse:
    transcription_length = len(request.transcription)
    log.info("estimation_requested", transcription_chars=transcription_length)
    transcription = _enrich_transcription(request)
    try:
        result = await service.estimate(
            transcription,
            model=request.model,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            reasoning_effort=request.reasoning_effort,
            max_output_tokens=request.max_output_tokens,
            pre_call=request.pre_call,
            example_format=request.output_format.to_example_format(),
            num_examples=request.num_examples,
        )
    except LLMServiceError as exc:
        log.warning(
            "estimation_failed",
            error_type=exc.error_type,
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
    validation = (
        evaluate_estimation_structure(result["estimation"], result["finish_reason"])
        if request.evaluate
        else None
    )
    return EstimationResponse(**result, validation=validation)


@router.post("/estimate/stream")
async def create_estimation_stream(
    request: EstimationRequest,
    service: BaseLLMService = Depends(get_llm_service),
) -> StreamingResponse:
    transcription_length = len(request.transcription)
    log.info("estimation_stream_requested", transcription_chars=transcription_length)
    transcription = _enrich_transcription(request)

    async def generate():
        try:
            async for delta in service.estimate_stream(
                transcription,
                model=request.model,
                temperature=request.temperature,
                top_p=request.top_p,
                top_k=request.top_k,
                reasoning_effort=request.reasoning_effort,
                max_output_tokens=request.max_output_tokens,
                pre_call=request.pre_call,
                example_format=request.output_format.to_example_format(),
                num_examples=request.num_examples,
            ):
                yield delta
        except LLMServiceError as exc:
            log.warning(
                "estimation_stream_failed",
                error_type=exc.error_type,
                status_code=exc.status_code,
                detail=exc.message,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return StreamingResponse(generate(), media_type="text/plain")
