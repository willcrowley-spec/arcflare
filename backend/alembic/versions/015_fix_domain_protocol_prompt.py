"""Update discovery protocol prompts — schema is now API-enforced, structure uses flat format."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_OLD_PREFIX = "Respond with valid JSON only:"
_NEW_PREFIX = "Return a JSON object matching the enforced schema:"

_NEW_STRUCTURE_PROTOCOL = """Return a JSON object matching the enforced schema. Output a FLAT list of ALL items — processes, subprocesses, AND steps — with parent_name to express hierarchy. Do NOT nest children. Every leaf must be level "step".
{
  "processes": [
    {"name": "Lead Management", "level": "process", "parent_name": null, "description": "...", "narrative": "...", "confidence": 0.85, "needs_review": false, "artifacts": [{"type": "object", "api_name": "Lead"}]},
    {"name": "Lead Scoring", "level": "subprocess", "parent_name": "Lead Management", "description": "...", "narrative": "...", "confidence": 0.8, "needs_review": false, "artifacts": []},
    {"name": "Assign Lead Score", "level": "step", "parent_name": "Lead Scoring", "description": "...", "narrative": "...", "confidence": 0.75, "needs_review": true, "artifacts": [{"type": "flow", "api_name": "Lead_Score_Assignment"}]}
  ]
}"""


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
              AND operation_id != 'discovery_structure'
              AND content LIKE :like_pattern
            """
        ),
        {"old_prefix": _OLD_PREFIX, "new_prefix": _NEW_PREFIX, "like_pattern": f"%{_OLD_PREFIX}%"},
    )
    conn.execute(
        sa.text(
            """
            UPDATE prompt_blocks
            SET content = :new_content,
                version = version + 1,
                updated_at = NOW()
            WHERE block_type = 'protocol'
              AND operation_id = 'discovery_structure'
            """
        ),
        {"new_content": _NEW_STRUCTURE_PROTOCOL},
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
        {"old_prefix": _OLD_PREFIX, "new_prefix": _NEW_PREFIX, "like_pattern": f"%{_NEW_PREFIX}%"},
    )
