from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.config import LLMModel, settings
from app.foundation.guardrails.input import InputGuardrailViolation
from app.domain.schemas.estimation import EstimationResponse, OutputFormat
from app.domain.schemas.session import SessionCreateResponse, SessionListItem, SessionMessageResponse, SessionStateResponse
from app.foundation.attachments.attachment_service import (
    AttachmentService,
    AttachmentExtractionError,
    UnsupportedAttachmentType,
)
from app.generation.cag.cache_service import CachedEstimationService
from app.domain.estimation_service import EstimationService
from app.foundation.llm.error_mapper import LLMServiceError
from app.generation.conversation.metadata_extractor import MetadataExtractor
from app.generation.conversation.session_estimation_service import AttachmentPayload, SessionEstimationService
from app.generation.conversation.sessions import store

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

_INTERNAL_PROCESSING_ERROR_DETAIL = "Internal processing error"

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


def _get_session_estimation_service(
    estimation_service: Annotated[
        EstimationService | CachedEstimationService,
        Depends(_get_cached_estimation_service),
    ],
    attachment_svc: Annotated[AttachmentService, Depends(_get_attachment_service)],
    metadata_extractor: Annotated[MetadataExtractor, Depends(_get_metadata_extractor)],
) -> SessionEstimationService:
    return SessionEstimationService(
        estimation_service=estimation_service,
        attachment_service=attachment_svc,
        metadata_extractor=metadata_extractor,
    )


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


@router.get("/{session_id}", responses={404: {"description": "Session not found"}})
async def get_session_state(session_id: str) -> SessionStateResponse:
    """Return persisted conversation history, metadata, and critical information anchors."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    summarizer = session.get_summarizer()
    anchors = summarizer.get_anchors()
    messages = session.history.messages()

    from app.domain.schemas.session import AnchorResponse

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
    session_estimation_service: Annotated[SessionEstimationService, Depends(_get_session_estimation_service)],
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

    attachment_payloads: list[AttachmentPayload] = []
    for upload in attachments:
        raw = await upload.read()
        attachment_payloads.append(
            AttachmentPayload(
                filename=upload.filename or "unknown",
                content_type=upload.content_type or "",
                data=raw,
            )
        )

    try:
        response = await session_estimation_service.estimate(
            session=session,
            transcript=transcript,
            attachments=attachment_payloads,
            model=model,
            temperature=temperature,
            pre_call=pre_call,
            output_format=output_format,
            prompt_version=prompt_version,
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
    except UnsupportedAttachmentType:
        raise HTTPException(status_code=422, detail="Unsupported attachment type")
    except AttachmentExtractionError:
        raise HTTPException(status_code=422, detail="Attachment extraction failed")
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        log.error("session_estimation_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=500, detail=_INTERNAL_PROCESSING_ERROR_DETAIL)

    return response


