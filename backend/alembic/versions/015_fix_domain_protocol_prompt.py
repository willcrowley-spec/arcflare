"""Strengthen discovery_domain protocol prompt to require JSON object root."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_OLD_PREFIX = "Respond with valid JSON only:"
_NEW_PREFIX = 'Respond with ONLY a valid JSON object (not an array). The root MUST be an object with a "domains" key:'


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE prompt_blocks
            SET content = REPLACE(content, :old_prefix, :new_prefix),
                version = version + 1,
                updated_at = NOW()
            WHERE operation_id = 'discovery_domain'
              AND block_type = 'protocol'
              AND content LIKE :like_pattern
            """
        ),
        {"old_prefix": _OLD_PREFIX, "new_prefix": _NEW_PREFIX, "like_pattern": f"{_OLD_PREFIX}%"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE prompt_blocks
            SET content = REPLACE(content, :new_prefix, :old_prefix),
                version = version + 1,
                updated_at = NOW()
            WHERE operation_id = 'discovery_domain'
              AND block_type = 'protocol'
              AND content LIKE :like_pattern
            """
        ),
        {"old_prefix": _NEW_PREFIX, "new_prefix": _OLD_PREFIX, "like_pattern": f"{_NEW_PREFIX}%"},
    )
