"""Agent opportunity engine: JSON and domain columns on recommendations.

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column(
            "agent_opportunity_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "linked_step_ids",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "domain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_processes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "financial_evaluation_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index(
        "ix_recommendations_domain_id", "recommendations", ["domain_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_domain_id", table_name="recommendations")
    op.drop_column("recommendations", "financial_evaluation_status")
    op.drop_column("recommendations", "domain_id")
    op.drop_column("recommendations", "linked_step_ids")
    op.drop_column("recommendations", "agent_opportunity_json")
