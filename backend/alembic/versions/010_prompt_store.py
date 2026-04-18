"""Create prompt_blocks and prompt_optimization_runs; seed system default prompt text."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.services.prompts.seeds import SEED_BLOCKS

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_blocks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("operation_id", sa.String(64), nullable=False, index=True),
        sa.Column("block_type", sa.String(64), nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "forked_from_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "operation_id",
            "block_type",
            "org_id",
            "status",
            name="uq_prompt_block_active",
        ),
    )

    op.create_table(
        "prompt_optimization_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("block_type", sa.String(64), nullable=False),
        sa.Column("optimizer", sa.String(32), nullable=False),
        sa.Column("metric_name", sa.String(128), nullable=False),
        sa.Column("metric_score_before", sa.Float(), nullable=True),
        sa.Column("metric_score_after", sa.Float(), nullable=True),
        sa.Column(
            "result_block_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    prompt_blocks_table = sa.table(
        "prompt_blocks",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("operation_id", sa.String(64)),
        sa.column("block_type", sa.String(64)),
        sa.column("org_id", UUID(as_uuid=True)),
        sa.column("content", sa.Text()),
        sa.column("version", sa.Integer()),
        sa.column("status", sa.String(16)),
        sa.column("forked_from_id", UUID(as_uuid=True)),
        sa.column("created_by", UUID(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for block in SEED_BLOCKS:
        rows.append(
            {
                "id": uuid.uuid4(),
                "operation_id": block["operation_id"],
                "block_type": block["block_type"],
                "org_id": None,
                "content": block["content"],
                "version": 1,
                "status": "active",
                "forked_from_id": None,
                "created_by": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    op.bulk_insert(prompt_blocks_table, rows)


def downgrade() -> None:
    op.drop_table("prompt_optimization_runs")
    op.drop_table("prompt_blocks")
