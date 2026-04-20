"""Add evidence_sources JSONB to business_processes and process_handoffs.

Revision ID: 021
Revises: 020
"""
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE business_processes "
        "ADD COLUMN IF NOT EXISTS evidence_sources JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE process_handoffs "
        "ADD COLUMN IF NOT EXISTS evidence_sources JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE process_handoffs DROP COLUMN IF EXISTS evidence_sources")
    op.execute("ALTER TABLE business_processes DROP COLUMN IF EXISTS evidence_sources")
