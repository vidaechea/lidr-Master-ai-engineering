"""Service layer for RAG pipeline estimations."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.estimation import RagEstimation
from app.services import ai_client

log = structlog.get_logger(__name__)


class RagEstimationService:
    """Business logic for RAG pipeline estimations."""

    async def estimate_from_transcript(
        self,
        session: AsyncSession,
        user_id: UUID,
        transcript: str,
        *,
        project_id: Optional[UUID] = None,
        top_k: Optional[int] = None,
        distance_threshold: Optional[float] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute RAG pipeline estimation and persist result.

        Args:
            session: Database session
            user_id: Owner user ID
            transcript: Input transcript (20-50k chars)
            project_id: Optional project association
            top_k: Top-k retrieval (1-50)
            distance_threshold: Semantic distance threshold (0.0-1.0)
            idempotency_key: Optional idempotency key for caching

        Returns:
            Full RAG estimation response dict
        """
        started = time.time()

        # Build request payload
        request_payload = {
            "transcript": transcript,
            "top_k": top_k,
            "distance_threshold": distance_threshold,
            "idempotency_key": idempotency_key,
        }

        # Call AI engine
        try:
            result = await ai_client.rag_estimate(request_payload)
            processing_time_ms = int((time.time() - started) * 1000)

            # Persist to database
            estimation = RagEstimation(
                user_id=user_id,
                project_id=project_id,
                transcript=transcript,
                idempotency_key=idempotency_key,
                request_params=request_payload,
                status="completed",
                processing_time_ms=processing_time_ms,
                pipeline_result=result,
                final_estimate=result.get("generation", {}).get("estimate"),
                retrieval_metadata={
                    "low_confidence": result.get("retrieval", {}).get("retrieval", {}).get("low_confidence"),
                    "candidates_evaluated": result.get("retrieval", {}).get("retrieval", {}).get("candidates_evaluated"),
                },
                low_confidence=result.get("generation", {}).get("estimate", {}).get("low_confidence", False),
                source_ids=result.get("generation", {}).get("estimate", {}).get("sources", []),
                completed_at=datetime.now(timezone.utc),
            )

            session.add(estimation)
            await session.flush()

            log.info(
                "rag_estimation_completed",
                user_id=str(user_id),
                project_id=str(project_id) if project_id else None,
                estimation_id=str(estimation.id),
                processing_time_ms=processing_time_ms,
            )

            return result

        except Exception as e:
            processing_time_ms = int((time.time() - started) * 1000)
            error_detail = str(e)

            # Persist failure
            estimation = RagEstimation(
                user_id=user_id,
                project_id=project_id,
                transcript=transcript,
                idempotency_key=idempotency_key,
                request_params=request_payload,
                status="failed",
                processing_time_ms=processing_time_ms,
                error_detail=error_detail,
                completed_at=datetime.now(timezone.utc),
            )

            session.add(estimation)
            await session.flush()

            log.error(
                "rag_estimation_failed",
                user_id=str(user_id),
                error=error_detail,
                processing_time_ms=processing_time_ms,
            )
            raise

    async def get_estimation(
        self,
        session: AsyncSession,
        user_id: UUID,
        estimation_id: UUID,
    ) -> Optional[RagEstimation]:
        """Retrieve a RAG estimation by ID."""
        from sqlalchemy import and_, select

        result = await session.execute(
            select(RagEstimation).where(
                and_(
                    RagEstimation.id == estimation_id,
                    RagEstimation.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_estimations(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RagEstimation]:
        """List RAG estimations for a user with optional filters."""
        from sqlalchemy import and_, select

        filters = [RagEstimation.user_id == user_id]

        if project_id:
            filters.append(RagEstimation.project_id == project_id)
        if status:
            filters.append(RagEstimation.status == status)

        result = await session.execute(
            select(RagEstimation)
            .where(and_(*filters))
            .order_by(RagEstimation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
