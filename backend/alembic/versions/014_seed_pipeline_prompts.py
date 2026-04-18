"""Seed prompt_blocks for new discovery pipeline operations and clean up legacy."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.services.prompts.seeds import SEED_BLOCKS

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

_NEW_OPERATIONS = {
    "discovery_structure",
    "discovery_enrichment",
    "discovery_flow",
    "discovery_validation",
}

_UPDATED_OPERATIONS = {
    "discovery_domain",
    "discovery_synthesis",
}

_REMOVED_OPERATION = "discovery_decomposition"


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

    # Insert new pipeline operation seeds
    rows: list[dict] = []
    for block in SEED_BLOCKS:
        if block["operation_id"] in _NEW_OPERATIONS:
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

    # Update existing system-level prompts for domain discovery and synthesis
    for block in SEED_BLOCKS:
        if block["operation_id"] in _UPDATED_OPERATIONS:
            op.execute(
                sa.text(
                    "UPDATE prompt_blocks SET content = :content, updated_at = :now "
                    "WHERE operation_id = :op AND block_type = :bt "
                    "AND org_id IS NULL AND status = 'active'"
                ).bindparams(
                    content=block["content"],
                    now=now,
                    op=block["operation_id"],
                    bt=block["block_type"],
                )
            )

    # Remove legacy decomposition rows
    op.execute(
        sa.text(
            "DELETE FROM prompt_blocks WHERE operation_id = :op"
        ).bindparams(op=_REMOVED_OPERATION)
    )


def downgrade() -> None:
    for op_id in _NEW_OPERATIONS:
        op.execute(
            sa.text(
                "DELETE FROM prompt_blocks WHERE operation_id = :op"
            ).bindparams(op=op_id)
        )
