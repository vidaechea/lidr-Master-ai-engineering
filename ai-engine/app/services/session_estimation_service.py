from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Sequence

import structlog

from app.config import LLMModel
from app.schemas.estimation import EstimationRequest, EstimationResponse, OutputFormat
from app.services.attachment_service import (
    AttachmentExtractionError,
    AttachmentService,
    ExtractedAttachment,
    UnsupportedAttachmentType,
)
from app.services.cache_service import CachedEstimationService
from app.services.estimation_service import EstimationService
from app.services.metadata_extractor import MetadataExtractor
from app.services.sessions import Session

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AttachmentPayload:
    filename: str
    content_type: str
    data: bytes


class SessionEstimationService:
    def __init__(
        self,
        estimation_service: EstimationService | CachedEstimationService,
        attachment_service: AttachmentService,
        metadata_extractor: MetadataExtractor,
    ) -> None:
        self._estimation_service = estimation_service
        self._attachment_service = attachment_service
        self._metadata_extractor = metadata_extractor

    async def estimate(
        self,
        session: Session,
        transcript: str,
        attachments: Sequence[AttachmentPayload],
        model: LLMModel | None,
        temperature: float | None,
        pre_call: bool,
        output_format: OutputFormat,
        prompt_version: str,
    ) -> EstimationResponse:
        start_time = time.time()
        extracted_texts = await self._extract_attachments(session.session_id, attachments)
        combined_transcript = self._attachment_service.build_combined_transcript(transcript, extracted_texts)

        log.info(
            "session_estimation_requested",
            session_id=session.session_id,
            transcript_chars=len(transcript),
            attachment_count=len(extracted_texts),
            combined_chars=len(combined_transcript),
        )

        request = EstimationRequest(
            transcription=combined_transcript,
            model=model,
            temperature=temperature,
            pre_call=pre_call,
            output_format=output_format,
        )

        attachments_total_chars = sum(len(attachment.text) for attachment in extracted_texts)
        response = await self._estimation_service.estimate_multi_turn(
            request,
            history=session.history,
            prompt_version=prompt_version,
            project_metadata=session.metadata,
            session_id=session.session_id,
            enriched_transcript_chars=len(combined_transcript),
            attachments_total_chars=attachments_total_chars,
            last_resolved_tier=session.last_resolved_tier,
        )

        session.metadata = self._metadata_extractor.update(
            transcript=combined_transcript,
            llm_response=response.estimation,
            existing=session.metadata,
        )
        log.debug(
            "session_metadata_updated",
            session_id=session.session_id,
            project_name=session.metadata.project_name,
            technologies=session.metadata.mentioned_technologies,
            team_size=session.metadata.assumed_team_size,
        )

        summarizer = session.get_summarizer()
        summarizer.process_turn(
            turn_number=session.history.turn_count,
            user_message=combined_transcript,
            assistant_response=response.estimation,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        log.debug(
            "session_estimation_completed",
            session_id=session.session_id,
            elapsed_ms=elapsed_ms,
            turn_count=session.history.turn_count,
        )
        return response

    async def _extract_attachments(
        self,
        session_id: str,
        attachments: Sequence[AttachmentPayload],
    ) -> list[ExtractedAttachment]:
        extracted_texts: list[ExtractedAttachment] = []
        for attachment in attachments:
            try:
                extracted = await asyncio.to_thread(
                    self._attachment_service.extract,
                    attachment.filename,
                    attachment.content_type,
                    attachment.data,
                )
                extracted_texts.append(extracted)
            except UnsupportedAttachmentType:
                log.warning(
                    "unsupported_attachment_type",
                    session_id=session_id,
                    filename=attachment.filename,
                    content_type=attachment.content_type,
                )
                raise
            except AttachmentExtractionError:
                log.error(
                    "attachment_extraction_failed",
                    session_id=session_id,
                    filename=attachment.filename,
                    content_type=attachment.content_type,
                )
                raise
        return extracted_texts