from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Valid tier values — product dimension, not authorization
USER_TIERS = ("developer", "pm", "executive")


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Kept nullable for backward compatibility with existing rows.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Product tier — controls the estimation template and output schema
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="developer")

    # Relationships
    projects: Mapped[list["Project"]] = relationship(back_populates="user", lazy="select")  # noqa: F821
    estimations: Mapped[list["Estimation"]] = relationship(back_populates="user", lazy="select")  # noqa: F821
