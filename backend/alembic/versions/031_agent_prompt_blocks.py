"""agent prompt blocks

Revision ID: 031
Revises: 030
Create Date: 2026-05-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


PROMPTS = [
    (
        "agent_opportunity",
        "instructions",
        """You are an Agentforce solution architect analyzing a business domain for automation opportunities.

Identify coherent clusters of work a single Agentforce agent could own across processes and steps. Separate business value from agent suitability: deterministic workflows, ETL/sync jobs, notification-only work, and integration brokers can be valuable recommendations, but they are not Agentforce candidates unless there is a bounded runtime reasoning job.

Only use Salesforce API names when they are present in the provided process touchpoints or metadata evidence. Data requirements are business copy, not deployable metadata truth.""",
    ),
    (
        "agent_opportunity",
        "protocol",
        """Return ONLY valid JSON with an agent_opportunities array and uncovered_processes array.

Each opportunity must include: agent_name, agent_type, description, topics, replaces, trigger, data_requirements, suggested_metadata_refs, integration_points, complexity_estimate, confidence, rationale, risks, and financial_signals.

Anti-patterns:
- No agent wrappers around deterministic Flow/Apex.
- No integration broker disguised as an agent.
- No notification-only agents.
- No one-agent-per-step.
- No domain mega-agents.
- No invented object or field API names.

Financial signal rules:
- estimated_actor_count means human people currently doing the work.
- estimated_hours_per_week_saved means total human effort saved per week across all actors.
- suggested_metadata_refs are untrusted hints; Arcflare validates them separately.""",
    ),
    (
        "agent_opportunity_cross_domain",
        "instructions",
        """Analyze domain-level opportunities across the full process landscape.

Look for cross-domain agent candidates only where shared context, ambiguity, exception handling, or judgment creates a real Agentforce runtime reasoning job. Preserve valuable deterministic automation or integration opportunities as non-agent findings.""",
    ),
    (
        "agent_opportunity_cross_domain",
        "protocol",
        """Return ONLY valid JSON with cross_domain_opportunities and merge_suggestions arrays.

Cross-domain opportunities use the same shape and rules as domain opportunities. Do not promote deterministic sync, ETL, notification, or integration-broker work into an agent candidate. Do not invent Salesforce metadata API names.""",
    ),
    (
        "agent_design_package",
        "instructions",
        """You are an Agentforce solution architect producing an Arcflare Agent Design Package.

Create a contract-first design package from validated recommendation evidence. Do not generate deployable source from business phrases. Every topic must map to explicit action contracts, every action must declare inputs and outputs, and Salesforce object access must become permission requirements. Missing evidence becomes a blocker instead of a guess.""",
    ),
    (
        "agent_design_package",
        "protocol",
        """Return ONLY valid JSON matching the Agent Design Package schema:
- agent: name, type, summary, trigger
- topics: jobs the agent owns
- session_variables: state carried through an agent turn
- action_contracts: explicit Apex/Flow/prompt contracts with inputs, outputs, permissions, and errors
- permission_requirements: exact object/operation requirements from validated bindings
- test_scenarios: business-readable tests
- blockers: missing evidence or dependencies
- observability_notes: logs, traces, metrics, and review points""",
    ),
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
            {
                "operation_id": operation_id,
                "block_type": block_type,
                "content": content,
            },
        )
        conn.execute(
            sa.text(
                """
                UPDATE prompt_blocks
                SET content = :content,
                    version = GREATEST(version, 1),
                    updated_at = now()
                WHERE operation_id = :operation_id
                  AND block_type = :block_type
                  AND org_id IS NULL
                  AND status = 'active'
                  AND btrim(content) = ''
                """
            ),
            {
                "operation_id": operation_id,
                "block_type": block_type,
                "content": content,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    for operation_id, block_type, _content in PROMPTS:
        conn.execute(
            sa.text(
                """
                DELETE FROM prompt_blocks
                WHERE operation_id = :operation_id
                  AND block_type = :block_type
                  AND org_id IS NULL
                  AND status = 'active'
                """
            ),
            {"operation_id": operation_id, "block_type": block_type},
        )
