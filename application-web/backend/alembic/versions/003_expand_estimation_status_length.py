"""Expand estimation status length for human review state.

Revision ID: 003_expand_estimation_status_length
Revises: 002_add_agent_profiles
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_expand_estimation_status_length"
down_revision = "002_add_agent_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "estimations",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "estimations",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=20),
        existing_nullable=False,
    )