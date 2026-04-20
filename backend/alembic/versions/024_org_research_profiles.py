"""Add org_research_profiles table.

Revision ID: 024
Revises: 023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_research_profiles",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("profile_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sources_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("facts_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("research_log_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("company_summary", sa.Text, nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("employee_range", sa.String(100), nullable=True),
        sa.Column("revenue_range", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("org_research_profiles")
