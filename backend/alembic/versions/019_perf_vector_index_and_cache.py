"""add HNSW vector index and discovery_cache table

Revision ID: 019
Revises: 018
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS discovery_cache (
            id UUID DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            prompt_hash VARCHAR(64) NOT NULL,
            operation VARCHAR(100) NOT NULL,
            model VARCHAR(200) NOT NULL,
            response_text TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0 NOT NULL,
            output_tokens INTEGER DEFAULT 0 NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_discovery_cache_org_id "
        "ON discovery_cache (org_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_discovery_cache_lookup "
        "ON discovery_cache (org_id, prompt_hash, operation)"
    )
    # HNSW index on document_chunks.embedding handled post-migration
    # (too large for synchronous build within healthcheck window)


def downgrade() -> None:
    op.drop_table("discovery_cache")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
