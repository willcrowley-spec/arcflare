"""Add platform_org_id to platform_connections with unique constraint."""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_connections",
        sa.Column("platform_org_id", sa.String(50), nullable=True),
    )
    op.create_index("ix_platform_connections_platform_org_id", "platform_connections", ["platform_org_id"])
    op.create_unique_constraint(
        "uq_connection_platform_org",
        "platform_connections",
        ["org_id", "platform_type", "platform_org_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_connection_platform_org", "platform_connections", type_="unique")
    op.drop_index("ix_platform_connections_platform_org_id", "platform_connections")
    op.drop_column("platform_connections", "platform_org_id")
