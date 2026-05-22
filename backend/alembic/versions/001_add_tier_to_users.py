"""add tier to users

Revision ID: 001_add_tier_to_users
Revises:
Create Date: 2026-05-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001_add_tier_to_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tier",
            sa.String(20),
            nullable=False,
            server_default="developer",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "tier")
