"""Intelligence pipeline columns on business_processes and discovery_runs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "business_processes",
        sa.Column(
            "trigger_conditions",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column(
            "decision_logic",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column(
            "system_touchpoints",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column(
            "success_criteria",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column(
            "failure_modes",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "business_processes",
        sa.Column("value_classification", sa.String(20), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column("complexity_score", sa.String(20), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column("automation_potential", sa.String(20), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column("estimated_duration", sa.String(20), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column("estimated_frequency", sa.String(20), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column(
            "sequencing",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "discovery_runs",
        sa.Column(
            "quality_scores",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "discovery_runs",
        sa.Column(
            "stage_results",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.drop_column("business_processes", "efficiency_score")
    op.drop_column("business_processes", "automation_level")


def downgrade() -> None:
    op.add_column(
        "business_processes",
        sa.Column("efficiency_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "business_processes",
        sa.Column("automation_level", sa.String(50), nullable=True),
    )
    op.drop_column("discovery_runs", "stage_results")
    op.drop_column("discovery_runs", "quality_scores")
    op.drop_column("business_processes", "sequencing")
    op.drop_column("business_processes", "estimated_frequency")
    op.drop_column("business_processes", "estimated_duration")
    op.drop_column("business_processes", "automation_potential")
    op.drop_column("business_processes", "complexity_score")
    op.drop_column("business_processes", "value_classification")
    op.drop_column("business_processes", "failure_modes")
    op.drop_column("business_processes", "success_criteria")
    op.drop_column("business_processes", "system_touchpoints")
    op.drop_column("business_processes", "decision_logic")
    op.drop_column("business_processes", "trigger_conditions")
