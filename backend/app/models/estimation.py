from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Estimation lifecycle states
EstimationStatus = str  # "pending" | "processing" | "completed" | "failed"


class Estimation(Base):
    __tablename__ = "estimations"

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional: an estimation may belong to a project or be standalone.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Input ─────────────────────────────────────────────────────────────────
    transcription: Mapped[str] = mapped_column(Text, nullable=False)
    # Full EstimationRequest dict serialised as JSONB for audit/replay.
    request_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Processing ────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Output ────────────────────────────────────────────────────────────────
    estimation_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Typed EstimationResult serialised as JSONB (phases, totals, confidence).
    structured_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Cost / tokens ─────────────────────────────────────────────────────────
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    # ── Error / completion ────────────────────────────────────────────────────
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When None, the estimation has not yet completed (status != "completed").
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(back_populates="estimations")  # noqa: F821
    project: Mapped["Project | None"] = relationship(back_populates="estimations")  # noqa: F821
