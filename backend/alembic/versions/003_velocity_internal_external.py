"""Add internal_active_count and external_active_count to user_velocity_snapshots.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_velocity_snapshots",
        sa.Column("internal_active_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_velocity_snapshots",
        sa.Column("external_active_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("user_velocity_snapshots", "external_active_count")
    op.drop_column("user_velocity_snapshots", "internal_active_count")
