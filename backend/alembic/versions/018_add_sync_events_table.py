"""add sync_events table

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("phase", sa.String(50), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "detail_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "severity",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sync_events_connection_id", "sync_events", ["connection_id"])
    op.create_index(
        "ix_sync_events_connection_run",
        "sync_events",
        ["connection_id", "run_id", "sequence"],
    )
    op.create_index("ix_sync_events_run_id", "sync_events", ["run_id"])
    op.create_index(
        "ix_sync_events_connection_created",
        "sync_events",
        ["connection_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_events_connection_created", table_name="sync_events")
    op.drop_index("ix_sync_events_run_id", table_name="sync_events")
    op.drop_index("ix_sync_events_connection_run", table_name="sync_events")
    op.drop_index("ix_sync_events_connection_id", table_name="sync_events")
    op.drop_table("sync_events")
