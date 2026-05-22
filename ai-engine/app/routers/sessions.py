import asyncio
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.config import LLMModel, settings
from app.guardrails.input import InputGuardrailViolation
from app.schemas.estimation import EstimationRequest, EstimationResponse, OutputFormat
from app.schemas.observation import CacheHitKind, TurnObservedEvent
from app.schemas.session import SessionCreateResponse, SessionListItem, SessionMessageResponse, SessionStateResponse
from app.services.attachment_service import (
    AttachmentService,
    AttachmentExtractionError,
    UnsupportedAttachmentType,
)
from app.services.cache_service import CachedEstimationService
from app.services.estimation_service import EstimationService
from app.services.helpers.error_mapper import LLMServiceError
from app.services.metadata_extractor import MetadataExtractor
from app.services.sessions import store

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

_LLM_ERROR_RESPONSES = {
    400: {"description": "Invalid request parameters"},
    401: {"description": "Invalid or missing API key"},
    404: {"description": "Session not found"},
    413: {"description": "Prompt exceeds model context window"},
    422: {"description": "Unsupported attachment type or extraction failure"},
    429: {"description": "Rate limit reached or insufficient credit"},
    500: {"description": "Unexpected server error"},
    503: {"description": "Provider unavailable or connection error"},
    504: {"description": "Provider request timed out"},
}


def _get_estimation_service() -> EstimationService:
    return EstimationService()


def _get_cached_estimation_service() -> EstimationService | CachedEstimationService:
    service = EstimationService()
    if settings.cache_enabled:
        return CachedEstimationService(service)
    return service


def _get_attachment_service() -> AttachmentService:
    return AttachmentService()


def _get_metadata_extractor() -> MetadataExtractor:
    return MetadataExtractor()


@router.post("", status_code=201)
async def create_session() -> SessionCreateResponse:
    """Create an empty conversational session and return its identifier.

    The returned ``session_id`` must be included in every subsequent estimation
    request so the service can retrieve and update the conversation history.
    """
    session = store.create()
    log.info("session_created", session_id=session.session_id)
    return SessionCreateResponse(session_id=session.session_id)


@router.get("")
async def list_sessions() -> list[SessionListItem]:
    """List all active sessions with basic metadata."""
    result = []
    for session in store.get_all():
        # Get the last assistant message for preview
        messages = session.history.messages()
        last_message = None
        for msg in reversed(messages):
            if msg.role == "assistant":
                last_message = msg.content[:200]
                break
        
        item = SessionListItem(
            session_id=session.session_id,
            project_name=session.metadata.project_name,
            turn_count=session.history.turn_count,
            last_message_content=last_message,
        )
        result.append(item)
    
    log.debug("sessions_listed", count=len(result))
    return result


@router.get("/{session_id}")
async def get_session_state(session_id: str) -> SessionStateResponse:
    """Return persisted conversation history, metadata, and critical information anchors."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    summarizer = session.get_summarizer()
    anchors = summarizer.get_anchors()
    messages = session.history.messages()

    from app.schemas.session import AnchorResponse

    return SessionStateResponse(
        session_id=session.session_id,
        project_metadata=session.metadata,
        history=[
            SessionMessageResponse(role=message.role, content=message.content)
            for message in messages
        ],
        turn_count=session.history.turn_count,
        message_count=len(messages),
        anchors_count=summarizer.anchor_count(),
        summary_chars=summarizer.summary_char_count(),
        last_resolved_tier=session.last_resolved_tier,
        last_tier_rule=session.last_tier_rule,
        anchors=[
            AnchorResponse(
                turn_number=anchor.turn_number,
                anchor_type=anchor.anchor_type,
                key_information=anchor.key_information,
                summary=anchor.summary,
            )
            for anchor in anchors
        ],
    )


@router.post(
    "/{session_id}/estimate",
    responses=_LLM_ERROR_RESPONSES,
)
async def create_session_estimation(
    session_id: str,
    estimation_service: Annotated[
        EstimationService | CachedEstimationService,
        Depends(_get_cached_estimation_service),
    ],
    attachment_svc: Annotated[AttachmentService, Depends(_get_attachment_service)],
    metadata_extractor: Annotated[MetadataExtractor, Depends(_get_metadata_extractor)],
    transcript: Annotated[
        str,
        Form(min_length=20, description="Meeting transcription or project description to estimate"),
    ],
    attachments: Annotated[
        list[UploadFile],
        File(description="Optional PDF, DOCX, or plain-text files with complementary documentation"),
    ] = [],
    model: Annotated[
        LLMModel | None,
        Form(description="Override the default model for this request"),
    ] = None,
    temperature: Annotated[
        float | None,
        Form(ge=0.0, le=2.0, description="Sampling temperature (non-reasoning models only)"),
    ] = None,
    pre_call: Annotated[
        bool,
        Form(description="Extract structured requirements before the main estimation call"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        Form(description="Desired output structure for the estimation"),
    ] = OutputFormat.PHASES_TABLE,
    prompt_version: Annotated[
        str,
        Query(description="Prompt template version to use (e.g. v1, v2)"),
    ] = settings.prompt_version,
) -> EstimationResponse:
    """Run an estimation for an existing session, optionally enriched with file attachments.

    Accepts ``multipart/form-data`` with a ``transcript`` field and an optional
    list of ``attachments`` (PDF, DOCX, or plain-text files).  Text is extracted
    locally and concatenated to the transcript before being sent to the LLM.
    """
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    # ------------------------------------------------------------------ #
    # Extract text from each attachment (CPU-bound → thread pool)         #
    # ------------------------------------------------------------------ #
    extracted_texts = []
    for upload in attachments:
        raw = await upload.read()
        content_type = upload.content_type or ""
        filename = upload.filename or "unknown"
        try:
            extracted = await asyncio.to_thread(
                attachment_svc.extract, filename, content_type, raw
            )
            extracted_texts.append(extracted)
        except UnsupportedAttachmentType as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except AttachmentExtractionError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    combined_transcript = attachment_svc.build_combined_transcript(transcript, extracted_texts)

    log.info(
        "session_estimation_requested",
        session_id=session_id,
        transcript_chars=len(transcript),
        attachment_count=len(extracted_texts),
        combined_chars=len(combined_transcript),
    )

    # ------------------------------------------------------------------ #
    # Delegate to estimation service                                       #
    # ------------------------------------------------------------------ #
    request = EstimationRequest(
        transcription=combined_transcript,
        model=model,
        temperature=temperature,
        pre_call=pre_call,
        output_format=output_format,
    )

    # Calculate total attachment size
    attachments_total_chars = sum(len(text) for text in extracted_texts)

    try:
        response = await estimation_service.estimate_multi_turn(
            request,
            history=session.history,
            prompt_version=prompt_version,
            project_metadata=session.metadata,
            session_id=session_id,
            enriched_transcript_chars=len(combined_transcript),
            attachments_total_chars=attachments_total_chars,
            last_resolved_tier=session.last_resolved_tier,
        )
    except InputGuardrailViolation as exc:
        _GUARDRAIL_STATUS: dict[str, int] = {
            "moderation": 400,
            "prompt_injection": 422,
            "pii": 422,
        }
        raise HTTPException(
            status_code=_GUARDRAIL_STATUS.get(exc.reason, 422),
            detail={"message": exc.message, "reason": exc.reason},
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        log.error("session_estimation_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    # ------------------------------------------------------------------ #
    # Update session metadata from this turn (heuristic, in-place)        #
    # ------------------------------------------------------------------ #
    session.metadata = metadata_extractor.update(
        transcript=combined_transcript,
        llm_response=response.estimation,
        existing=session.metadata,
    )
    log.debug(
        "session_metadata_updated",
        session_id=session_id,
        project_name=session.metadata.project_name,
        technologies=session.metadata.mentioned_technologies,
        team_size=session.metadata.assumed_team_size,
    )

    # ------------------------------------------------------------------ #
    # Process turn through summarizer to generate anchors                 #
    # ------------------------------------------------------------------ #
    summarizer = session.get_summarizer()
    turn_number = session.history.turn_count  # Current turn (already incremented by estimate_multi_turn)
    anchors = summarizer.process_turn(
        turn_number=turn_number,
        user_message=combined_transcript,
        assistant_response=response.estimation,
    )

    # ------------------------------------------------------------------ #
    # Emit unified turn_observed event with all context                  #
    # ------------------------------------------------------------------ #
    turn_observed = TurnObservedEvent(
        turn_index=turn_number,
        session_id=session_id,
        enriched_transcript_chars=len(combined_transcript),
        attachments_total_chars=attachments_total_chars,
        messages_in_window=len(session.history.messages()),
        anchors_count=len(anchors) if anchors else 0,
        summary_chars=summarizer.summary_char_count(),
        tokens_in=response.input_tokens,
        tokens_out=response.output_tokens,
        cost_usd=response.turn_cost_usd,
        latency_ms=0.0,  # Measured in estimate_multi_turn, available in logs
        cache_hit_kind=CacheHitKind.NONE,  # Set to exact/semantic if cached hit occurred
        last_resolved_tier=session.last_resolved_tier,
        model=response.model,
        response_id=response.response_id,
    )
    log.info("turn_observed", **turn_observed.model_dump())

    return response
