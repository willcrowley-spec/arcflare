"""Rename classification 'empty' to 'deprecated' in metadata_objects."""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE metadata_objects SET classification = 'deprecated' WHERE classification = 'empty'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE metadata_objects SET classification = 'empty' WHERE classification = 'deprecated'"
    )
