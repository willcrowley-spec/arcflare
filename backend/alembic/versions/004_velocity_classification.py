"""Add by_created_month_json and system_user_count to user_velocity_snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_velocity_snapshots",
        sa.Column("by_created_month_json", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "user_velocity_snapshots",
        sa.Column("system_user_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("user_velocity_snapshots", "system_user_count")
    op.drop_column("user_velocity_snapshots", "by_created_month_json")
