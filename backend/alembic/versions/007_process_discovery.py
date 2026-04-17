"""Add discovery_runs, process_handoffs, and new business_process columns."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pass_results", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
        sa.Column("error", sa.Text(), nullable=True),
    )

    op.add_column(
        "business_processes",
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_processes.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column("level", sa.String(50), nullable=False, server_default="process"),
    )
    op.add_column(
        "business_processes",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "business_processes",
        sa.Column("narrative", sa.Text(), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column(
            "discovery_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column("actors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "business_processes",
        sa.Column("artifacts", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    op.create_table(
        "process_handoffs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "source_process_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_processes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "target_process_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_processes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("handoff_type", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_gap", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "discovery_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_table("process_handoffs")
    op.drop_column("business_processes", "artifacts")
    op.drop_column("business_processes", "actors")
    op.drop_column("business_processes", "discovery_run_id")
    op.drop_column("business_processes", "narrative")
    op.drop_column("business_processes", "needs_review")
    op.drop_column("business_processes", "confidence_score")
    op.drop_column("business_processes", "level")
    op.drop_column("business_processes", "parent_id")
    op.drop_table("discovery_runs")
