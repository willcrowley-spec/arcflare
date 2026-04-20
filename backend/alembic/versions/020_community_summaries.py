"""add source, summary, summary_embedding to communities

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE communities "
        "ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'document'"
    )
    op.execute(
        "ALTER TABLE communities ADD COLUMN IF NOT EXISTS summary TEXT"
    )
    op.execute(
        "ALTER TABLE communities "
        "ADD COLUMN IF NOT EXISTS summary_embedding vector(3072)"
    )

    op.execute(
        "UPDATE communities SET source = 'metadata' "
        "WHERE source = 'document' AND metadata_json->>'source' = 'metadata_graph'"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_communities_source "
        "ON communities (source)"
    )
    # No vector index needed — communities table is tiny (10-30 rows per org).
    # Sequential scan with cosine distance is effectively instant.


def downgrade() -> None:
    pass  # no vector index to drop
    op.execute("ALTER TABLE communities DROP COLUMN IF EXISTS summary_embedding")
    op.drop_index("ix_communities_source", table_name="communities")
    op.drop_column("communities", "summary")
    op.drop_column("communities", "source")
