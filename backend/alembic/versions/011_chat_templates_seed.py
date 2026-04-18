"""Seed chat_templates gap_opener prompt block."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.services.prompts.seeds import SEED_BLOCKS

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_NEW_OPERATION = "chat_templates"


def upgrade() -> None:
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
        if block["operation_id"] == _NEW_OPERATION:
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
    if rows:
        op.bulk_insert(prompt_blocks_table, rows)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM prompt_blocks WHERE operation_id = :op").bindparams(
            op=_NEW_OPERATION
        )
    )
