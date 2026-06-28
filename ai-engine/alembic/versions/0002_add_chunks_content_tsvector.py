"""Add generated TSVECTOR column for lexical search over chunk content."""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('spanish'::regconfig, coalesce(content, ''))
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_chunks_content_tsv_gin
        ON chunks
        USING gin (content_tsv)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv_gin")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
