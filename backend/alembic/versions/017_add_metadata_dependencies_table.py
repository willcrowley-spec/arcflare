"""add metadata_dependencies table

Revision ID: 017
Revises: 016
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metadata_dependencies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_api_name", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_api_name", sa.String(255), nullable=False),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_metadata_dependencies_org_id", "metadata_dependencies", ["org_id"])
    op.create_index(
        "ix_metadata_dependencies_connection_id", "metadata_dependencies", ["connection_id"]
    )
    op.create_index(
        "ix_metadata_deps_source",
        "metadata_dependencies",
        ["connection_id", "source_type", "source_api_name"],
    )
    op.create_index(
        "ix_metadata_deps_target",
        "metadata_dependencies",
        ["connection_id", "target_type", "target_api_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_metadata_deps_target", table_name="metadata_dependencies")
    op.drop_index("ix_metadata_deps_source", table_name="metadata_dependencies")
    op.drop_index("ix_metadata_dependencies_connection_id", table_name="metadata_dependencies")
    op.drop_index("ix_metadata_dependencies_org_id", table_name="metadata_dependencies")
    op.drop_table("metadata_dependencies")
