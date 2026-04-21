"""Recommendation pipeline: recommendation_runs table and recommendation columns.

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_runs",
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
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column(
            "config",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "stage_results",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "recommendation_type",
            sa.String(20),
            nullable=False,
            server_default="discovered",
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "automation_type",
            sa.String(20),
            nullable=False,
            server_default="hybrid",
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column("base_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column("llm_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column("llm_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "score_divergence_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "assumptions_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "scenarios_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "enrichment_log",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "recommendation_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recommendation_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "recommendation_run_id")
    op.drop_column("recommendations", "enrichment_log")
    op.drop_column("recommendations", "scenarios_json")
    op.drop_column("recommendations", "assumptions_json")
    op.drop_column("recommendations", "score_divergence_flag")
    op.drop_column("recommendations", "llm_rationale")
    op.drop_column("recommendations", "llm_score")
    op.drop_column("recommendations", "base_score")
    op.drop_column("recommendations", "automation_type")
    op.drop_column("recommendations", "recommendation_type")
    op.drop_table("recommendation_runs")
