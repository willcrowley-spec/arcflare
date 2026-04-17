"""Add classification, velocity_score to metadata_objects; analysis_config to organizations; drop deprecated columns."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

DEFAULT_ANALYSIS_CONFIG = {
    "velocity_window_days": 30,
    "classification_threshold": 0.1,
    "min_records_for_vectorization": 1,
    "embedding_provider": "default",
    "vector_store_provider": "default",
    "llm_provider": "default",
}


def upgrade() -> None:
    op.add_column("metadata_objects", sa.Column("classification", sa.String(20), nullable=True))
    op.add_column("metadata_objects", sa.Column("classification_source", sa.String(10), nullable=False, server_default="auto"))
    op.add_column("metadata_objects", sa.Column("velocity_score", sa.Float(), nullable=False, server_default="0.0"))
    op.create_index("ix_metadata_objects_classification", "metadata_objects", ["classification"])
    op.drop_column("metadata_objects", "has_triggers")
    op.drop_column("metadata_objects", "has_flows")
    op.drop_column("metadata_objects", "has_validation_rules")
    op.drop_column("metadata_objects", "last_synced_at")
    op.add_column(
        "organizations",
        sa.Column(
            "analysis_config",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{\"velocity_window_days\":30,\"classification_threshold\":0.1,\"min_records_for_vectorization\":1,\"embedding_provider\":\"default\",\"vector_store_provider\":\"default\",\"llm_provider\":\"default\"}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "analysis_config")
    op.drop_index("ix_metadata_objects_classification", table_name="metadata_objects")
    op.drop_column("metadata_objects", "velocity_score")
    op.drop_column("metadata_objects", "classification_source")
    op.drop_column("metadata_objects", "classification")
    op.add_column("metadata_objects", sa.Column("has_triggers", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("metadata_objects", sa.Column("has_flows", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("metadata_objects", sa.Column("has_validation_rules", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("metadata_objects", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
