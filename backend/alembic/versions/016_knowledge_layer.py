"""knowledge layer: concepts, communities, provenance

Revision ID: 016
Revises: 015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=True),
        sa.Column("concept_type", sa.String(50), nullable=False, server_default="noun_phrase"),
        sa.Column("frequency", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_concepts_org_name", "concepts", ["org_id", "name"])

    op.create_table(
        "concept_cooccurrences",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("concept_a_id", UUID(as_uuid=True), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept_b_id", UUID(as_uuid=True), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pmi_weight", sa.Float, nullable=True),
        sa.Column("document_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_unique_constraint(
        "uq_cooccurrence_org_pair",
        "concept_cooccurrences",
        ["org_id", "concept_a_id", "concept_b_id"],
    )

    op.create_table(
        "communities",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("communities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("label", sa.String(512), nullable=True),
        sa.Column("member_concept_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chunk_communities",
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("community_id", UUID(as_uuid=True), sa.ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "process_document_sources",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("chunk_content_hashes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True, index=True))
    op.add_column("documents", sa.Column("concept_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("community_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("documents", sa.Column("embedding_model", sa.String(128), nullable=True))

    op.add_column("document_chunks", sa.Column("concept_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("document_chunks", sa.Column("content_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "content_hash")
    op.drop_column("document_chunks", "concept_ids")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "community_ids")
    op.drop_column("documents", "concept_count")
    op.drop_column("documents", "content_hash")
    op.drop_table("process_document_sources")
    op.drop_table("chunk_communities")
    op.drop_table("communities")
    op.drop_table("concept_cooccurrences")
    op.drop_table("concepts")
