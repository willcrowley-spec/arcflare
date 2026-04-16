"""Initial schema - all tables

Revision ID: 001
Revises: 
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("clerk_org_id", sa.String(255), nullable=False, unique=True),
        sa.Column("plan_tier", sa.String(50), nullable=False, server_default="free"),
        sa.Column("settings_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_clerk_org_id", "organizations", ["clerk_org_id"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.String(255), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"])

    op.create_table(
        "platform_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_type", sa.String(50), nullable=False),
        sa.Column("instance_url", sa.String(512), nullable=True),
        sa.Column("oauth_tokens_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("entity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_connections_org_id", "platform_connections", ["org_id"])

    op.create_table(
        "metadata_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_name", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("object_type", sa.String(50), nullable=True),
        sa.Column("field_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("managed_package_namespace", sa.String(255), nullable=True),
        sa.Column("has_triggers", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_flows", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_validation_rules", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("connection_id", "api_name", name="uq_metadata_objects_connection_api_name"),
    )
    op.create_index("ix_metadata_objects_org_id", "metadata_objects", ["org_id"])
    op.create_index("ix_metadata_objects_connection_id", "metadata_objects", ["connection_id"])

    op.create_table(
        "metadata_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_name", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("field_type", sa.String(100), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_unique", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("relationship_to", sa.String(255), nullable=True),
        sa.Column("relationship_type", sa.String(50), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("object_id", "api_name", name="uq_metadata_fields_object_api_name"),
    )
    op.create_index("ix_metadata_fields_object_id", "metadata_fields", ["object_id"])

    op.create_table(
        "metadata_automation",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("automation_type", sa.String(50), nullable=False),
        sa.Column("api_name", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("related_object", sa.String(255), nullable=True),
        sa.Column("complexity_score", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("connection_id", "automation_type", "api_name", name="uq_metadata_automation_conn_type_api"),
    )
    op.create_index("ix_metadata_automation_connection_id", "metadata_automation", ["connection_id"])
    op.create_index("ix_metadata_automation_org_id", "metadata_automation", ["org_id"])

    op.create_table(
        "record_telemetry",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("created_count_delta", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("modified_count_delta", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_record_telemetry_object_id", "record_telemetry", ["object_id"])
    op.create_index("ix_record_telemetry_object_snapshot", "record_telemetry", ["object_id", "snapshot_at"])

    op.create_table(
        "business_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("headcount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("salesforce_user_id", sa.String(18), nullable=True),
        sa.Column("cost_data_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_business_entities_org_id", "business_entities", ["org_id"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="uploading"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(512), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(3072) USING embedding::vector(3072)")

    op.create_table(
        "business_processes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("efficiency_score", sa.Float(), nullable=True),
        sa.Column("automation_level", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("sub_process_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("managed_asset_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_business_processes_org_id", "business_processes", ["org_id"])

    op.create_table(
        "process_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("process_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("subtitle", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(100), nullable=True),
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_process_nodes_process_id", "process_nodes", ["process_id"])

    op.create_table(
        "process_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("process_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("process_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("process_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_label", sa.String(100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("process_id", "source_node_id", "target_node_id", name="uq_process_edges_process_src_tgt"),
    )
    op.create_index("ix_process_edges_process_id", "process_edges", ["process_id"])
    op.create_index("ix_process_edges_source_node_id", "process_edges", ["source_node_id"])
    op.create_index("ix_process_edges_target_node_id", "process_edges", ["target_node_id"])

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("estimated_roi", sa.Numeric(12, 2), nullable=True),
        sa.Column("composite_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("analysis_inputs_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("actions_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("impact_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("architecture_health_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("linked_process_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recommendations_org_id", "recommendations", ["org_id"])

    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("monthly_cap", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_spend", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="idle"),
        sa.Column("accuracy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("capability_tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("linked_recommendation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agents_org_id", "agents", ["org_id"])

    op.create_table(
        "agent_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(8, 4), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_usage_logs_agent_id", "agent_usage_logs", ["agent_id"])


def downgrade() -> None:
    op.drop_table("agent_usage_logs")
    op.drop_table("agents")
    op.drop_table("recommendations")
    op.drop_table("process_edges")
    op.drop_table("process_nodes")
    op.drop_table("business_processes")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("business_entities")
    op.drop_table("record_telemetry")
    op.drop_table("metadata_automation")
    op.drop_table("metadata_fields")
    op.drop_table("metadata_objects")
    op.drop_table("platform_connections")
    op.drop_table("users")
    op.drop_table("organizations")
