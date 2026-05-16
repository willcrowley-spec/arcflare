"""Switch recommendation prompts to portfolio qualification.

Revision ID: 034
Revises: 033
Create Date: 2026-05-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.services.prompts.seeds import SEED_BLOCKS


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


_OPERATIONS = {
    "agent_opportunity": {"instructions", "protocol"},
    "agent_opportunity_cross_domain": {"instructions", "protocol"},
    "agent_design_package": {"instructions", "protocol"},
}

PROMPTS = [
    (block["operation_id"], block["block_type"], block["content"])
    for block in SEED_BLOCKS
    if block["operation_id"] in _OPERATIONS
    and block["block_type"] in _OPERATIONS[block["operation_id"]]
]


def upgrade() -> None:
    conn = op.get_bind()
    for operation_id, block_type, content in PROMPTS:
        conn.execute(
            sa.text(
                """
                INSERT INTO prompt_blocks (
                    id, operation_id, block_type, org_id, content, version, status, created_at, updated_at
                )
                SELECT gen_random_uuid(), :operation_id, :block_type, NULL, :content, 1, 'active', now(), now()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM prompt_blocks
                    WHERE operation_id = :operation_id
                      AND block_type = :block_type
                      AND org_id IS NULL
                      AND status = 'active'
                )
                """
            ),
            {"operation_id": operation_id, "block_type": block_type, "content": content},
        )
        conn.execute(
            sa.text(
                """
                UPDATE prompt_blocks
                SET content = :content,
                    version = version + 1,
                    updated_at = now()
                WHERE operation_id = :operation_id
                  AND block_type = :block_type
                  AND org_id IS NULL
                  AND status = 'active'
                  AND content IS DISTINCT FROM :content
                """
            ),
            {"operation_id": operation_id, "block_type": block_type, "content": content},
        )


def downgrade() -> None:
    return None
