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
    op.add_column(
        "communities",
        sa.Column("source", sa.String(20), nullable=False, server_default="document"),
    )
    op.add_column(
        "communities",
        sa.Column("summary", sa.Text, nullable=True),
    )

    op.execute(
        "UPDATE communities SET source = 'metadata' "
        "WHERE metadata_json->>'source' = 'metadata_graph'"
    )

    op.create_index("ix_communities_source", "communities", ["source"])

    op.execute(
        "ALTER TABLE communities "
        "ADD COLUMN summary_embedding vector(3072)"
    )

    # HNSW index on summary_embedding — CONCURRENTLY to avoid blocking.
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_communities_summary_embedding_hnsw "
        "ON communities USING hnsw (summary_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_communities_summary_embedding_hnsw")
    op.execute("ALTER TABLE communities DROP COLUMN IF EXISTS summary_embedding")
    op.drop_index("ix_communities_source", table_name="communities")
    op.drop_column("communities", "summary")
    op.drop_column("communities", "source")
