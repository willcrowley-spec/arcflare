"""Graph, community detection, and vectorization pipeline overhaul.

- Add contextualized_content and embedding_model columns to document_chunks
- Change embedding dimensions from 3072 to 768 (MRL)
- Change community summary_embedding dimensions from 3072 to 768
- NULL out all existing embeddings (incompatible dimensions)
- Create HNSW index on document_chunks.embedding

Revision ID: 022
Revises: 021
"""
from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS contextualized_content TEXT"
    )
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(128)"
    )

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_ivfflat")

    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute("UPDATE communities SET summary_embedding = NULL")

    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)"
    )
    op.execute(
        "ALTER TABLE communities "
        "ALTER COLUMN summary_embedding TYPE vector(768) USING summary_embedding::vector(768)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_communities_summary_embedding_hnsw "
        "ON communities USING hnsw (summary_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_communities_summary_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")

    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute("UPDATE communities SET summary_embedding = NULL")

    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(3072) USING embedding::vector(3072)"
    )
    op.execute(
        "ALTER TABLE communities "
        "ALTER COLUMN summary_embedding TYPE vector(3072) USING summary_embedding::vector(3072)"
    )

    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS contextualized_content")
