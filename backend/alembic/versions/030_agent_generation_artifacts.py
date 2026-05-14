"""agent generation artifacts

Revision ID: 030
Revises: 029
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("current_stage", sa.String(length=100), nullable=True),
        sa.Column("model_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("stage_results", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_generation_runs_org_id"), "agent_generation_runs", ["org_id"], unique=False)
    op.create_index(
        op.f("ix_agent_generation_runs_recommendation_id"),
        "agent_generation_runs",
        ["recommendation_id"],
        unique=False,
    )

    op.create_table(
        "agent_design_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="draft", nullable=False),
        sa.Column("package_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("validation_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generation_run_id"], ["agent_generation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_design_packages_generation_run_id"), "agent_design_packages", ["generation_run_id"], unique=False)
    op.create_index(op.f("ix_agent_design_packages_org_id"), "agent_design_packages", ["org_id"], unique=False)
    op.create_index(op.f("ix_agent_design_packages_recommendation_id"), "agent_design_packages", ["recommendation_id"], unique=False)

    op.create_table(
        "agent_source_bundles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("design_package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="generated", nullable=False),
        sa.Column("source_tree_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("checks_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["design_package_id"], ["agent_design_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["agent_generation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_source_bundles_design_package_id"), "agent_source_bundles", ["design_package_id"], unique=False)
    op.create_index(op.f("ix_agent_source_bundles_generation_run_id"), "agent_source_bundles", ["generation_run_id"], unique=False)
    op.create_index(op.f("ix_agent_source_bundles_org_id"), "agent_source_bundles", ["org_id"], unique=False)

    op.create_table(
        "scratch_validation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="queued", nullable=False),
        sa.Column("devhub_alias", sa.String(length=255), nullable=True),
        sa.Column("scratch_org_id", sa.String(length=50), nullable=True),
        sa.Column("scratch_org_username", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("logs_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_bundle_id"], ["agent_source_bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scratch_validation_runs_org_id"), "scratch_validation_runs", ["org_id"], unique=False)
    op.create_index(op.f("ix_scratch_validation_runs_source_bundle_id"), "scratch_validation_runs", ["source_bundle_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scratch_validation_runs_source_bundle_id"), table_name="scratch_validation_runs")
    op.drop_index(op.f("ix_scratch_validation_runs_org_id"), table_name="scratch_validation_runs")
    op.drop_table("scratch_validation_runs")
    op.drop_index(op.f("ix_agent_source_bundles_org_id"), table_name="agent_source_bundles")
    op.drop_index(op.f("ix_agent_source_bundles_generation_run_id"), table_name="agent_source_bundles")
    op.drop_index(op.f("ix_agent_source_bundles_design_package_id"), table_name="agent_source_bundles")
    op.drop_table("agent_source_bundles")
    op.drop_index(op.f("ix_agent_design_packages_recommendation_id"), table_name="agent_design_packages")
    op.drop_index(op.f("ix_agent_design_packages_org_id"), table_name="agent_design_packages")
    op.drop_index(op.f("ix_agent_design_packages_generation_run_id"), table_name="agent_design_packages")
    op.drop_table("agent_design_packages")
    op.drop_index(op.f("ix_agent_generation_runs_recommendation_id"), table_name="agent_generation_runs")
    op.drop_index(op.f("ix_agent_generation_runs_org_id"), table_name="agent_generation_runs")
    op.drop_table("agent_generation_runs")
