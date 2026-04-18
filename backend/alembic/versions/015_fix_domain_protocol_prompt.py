"""Update discovery protocol prompts — schema is now API-enforced."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_OLD_PREFIX = "Respond with valid JSON only:"
_NEW_PREFIX = "Return a JSON object matching the enforced schema:"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE prompt_blocks
            SET content = REPLACE(content, :old_prefix, :new_prefix),
                version = version + 1,
                updated_at = NOW()
            WHERE block_type = 'protocol'
              AND operation_id LIKE 'discovery_%'
              AND content LIKE :like_pattern
            """
        ),
        {"old_prefix": _OLD_PREFIX, "new_prefix": _NEW_PREFIX, "like_pattern": f"%{_OLD_PREFIX}%"},
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
            WHERE block_type = 'protocol'
              AND operation_id LIKE 'discovery_%'
              AND content LIKE :like_pattern
            """
        ),
        {"old_prefix": _NEW_PREFIX, "new_prefix": _OLD_PREFIX, "like_pattern": f"%{_NEW_PREFIX}%"},
    )
