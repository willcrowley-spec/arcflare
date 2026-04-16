"""Add metadata_components, org_license_snapshots, user_velocity_snapshots tables.

Revision ID: 002
Revises: 001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metadata_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_category", sa.String(50), nullable=False),
        sa.Column("api_name", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("related_object", sa.String(255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_metadata_components_org_id", "metadata_components", ["org_id"])
    op.create_index("ix_metadata_components_connection_id", "metadata_components", ["connection_id"])
    op.create_unique_constraint(
        "uq_metadata_components_conn_cat_api",
        "metadata_components",
        ["connection_id", "component_category", "api_name"],
    )

    op.create_table(
        "org_license_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("edition", sa.String(100), nullable=True),
        sa.Column("is_sandbox", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("licenses_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("package_licenses_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("psl_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("limits_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("estimated_annual_spend", sa.Numeric(12, 2), nullable=True),
    )
    op.create_index("ix_org_license_snapshots_org_id", "org_license_snapshots", ["org_id"])
    op.create_index("ix_org_license_snapshots_connection_id", "org_license_snapshots", ["connection_id"])

    op.create_table(
        "user_velocity_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("active_user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_users_this_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deactivated_this_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("by_role_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("by_profile_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_user_velocity_snapshots_org_id", "user_velocity_snapshots", ["org_id"])
    op.create_index("ix_user_velocity_snapshots_connection_id", "user_velocity_snapshots", ["connection_id"])


def downgrade() -> None:
    op.drop_table("user_velocity_snapshots")
    op.drop_table("org_license_snapshots")
    op.drop_table("metadata_components")
