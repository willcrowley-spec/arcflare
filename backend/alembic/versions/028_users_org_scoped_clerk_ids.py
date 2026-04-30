"""Scope Clerk users by Arcflare organization.

Revision ID: 028
Revises: 027
Create Date: 2026-04-30
"""
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_clerk_user_id_key")
    op.create_unique_constraint(
        "uq_users_org_clerk_user",
        "users",
        ["org_id", "clerk_user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_org_clerk_user", "users", type_="unique")
    op.create_unique_constraint(
        "users_clerk_user_id_key",
        "users",
        ["clerk_user_id"],
    )
