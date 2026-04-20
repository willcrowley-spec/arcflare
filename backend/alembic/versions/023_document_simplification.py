"""Add summary and processing_phase columns to documents.

Revision ID: 023
Revises: 022
"""
from alembic import op
import sqlalchemy as sa


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("processing_phase", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_phase")
    op.drop_column("documents", "summary")
