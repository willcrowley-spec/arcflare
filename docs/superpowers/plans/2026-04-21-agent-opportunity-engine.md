# Agent Opportunity Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-process recommendation pipeline with a domain-level agent opportunity engine that identifies where Agentforce agents can replace work spanning multiple processes and steps.

**Architecture:** 4-phase pipeline — (1) domain context assembly from discovery data (pure Python), (2) per-domain LLM agent opportunity analysis with Agentforce knowledge reference, (3) cross-domain synthesis, (4) async financial evaluation via Celery. Replaces `candidate_generator.py`, `heuristic_scorer.py`, `llm_scorer.py`. Preserves `financial_engine.py` unchanged.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), Alembic, FastAPI, Celery, Pydantic v2, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-21-agent-opportunity-engine-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `backend/app/services/recommendations/domain_assembler.py` | Phase 1: Query DB, build structured `DomainContext` dicts per domain |
| `backend/app/services/recommendations/agent_analyzer.py` | Phase 2: LLM call per domain, parse response, resolve IDs |
| `backend/app/services/recommendations/cross_domain.py` | Phase 3: Cross-domain synthesis LLM call |
| `backend/alembic/versions/027_agent_opportunity_columns.py` | Migration: new columns on `recommendations` table |
| `backend/tests/services/recommendations/__init__.py` | Test package init |
| `backend/tests/services/recommendations/test_domain_assembler.py` | Unit tests for domain context assembly |
| `backend/tests/services/recommendations/test_agent_analyzer.py` | Unit tests for agent analyzer output parsing + ID resolution |
| `backend/tests/services/recommendations/test_pipeline_integration.py` | Integration tests for the full pipeline orchestration |

### Modified files

| File | Change |
|------|--------|
| `backend/app/models/recommendation.py` | Add 4 columns: `agent_opportunity_json`, `linked_step_ids`, `domain_id`, `financial_evaluation_status` |
| `backend/app/schemas/recommendation.py` | Add new fields to `RecommendationResponse`, add `AgentOpportunityDetail` schema |
| `backend/app/services/recommendations/pipeline.py` | Full rewrite: 4-phase orchestration replacing 4-stage pipeline |
| `backend/app/services/prompts/seeds.py` | Add `_AGENT_OPPORTUNITY_*` and `_AGENT_OPPORTUNITY_CROSS_DOMAIN_*` prompt blocks |
| `backend/app/services/ai/operations.py` | Add `agent_opportunity` and `agent_opportunity_cross_domain` operation configs |
| `backend/app/workers/analysis.py` | Add `evaluate_agent_financials_task` Celery task |
| `backend/app/api/routes/recommendations.py` | Add `confidence` sort, `financial_evaluation_status` to status response |
| `backend/app/services/chat/context.py` | Include `agent_opportunity_json` in recommendation anchor payload |

### Deprecated (delete after pipeline is working)

| File | Reason |
|------|--------|
| `backend/app/services/recommendations/heuristic_scorer.py` | No heuristic scoring in new pipeline |
| `backend/app/services/recommendations/candidate_generator.py` | Replaced by `domain_assembler.py` |
| `backend/app/services/recommendations/llm_scorer.py` | Replaced by `agent_analyzer.py` |

---

### Task 1: Database Migration — New Columns on Recommendations

**Files:**
- Create: `backend/alembic/versions/027_agent_opportunity_columns.py`

- [ ] **Step 1: Create the migration file**

```python
"""Agent opportunity engine: new columns on recommendations.

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column("agent_opportunity_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "recommendations",
        sa.Column("linked_step_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "domain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_processes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column("financial_evaluation_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_index("ix_recommendations_domain_id", "recommendations", ["domain_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_domain_id", table_name="recommendations")
    op.drop_column("recommendations", "financial_evaluation_status")
    op.drop_column("recommendations", "domain_id")
    op.drop_column("recommendations", "linked_step_ids")
    op.drop_column("recommendations", "agent_opportunity_json")
```

- [ ] **Step 2: Run the migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies cleanly, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/027_agent_opportunity_columns.py
git commit -m "migration: add agent opportunity columns to recommendations table"
```

---

### Task 2: Update Recommendation Model

**Files:**
- Modify: `backend/app/models/recommendation.py`

- [ ] **Step 1: Add new columns to the Recommendation model**

Add these after `enrichment_log` (around line 70) and before `recommendation_run_id`:

```python
    agent_opportunity_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    linked_step_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    domain_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_processes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    financial_evaluation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
```

- [ ] **Step 2: Verify the app starts**

Run: `cd backend && python -c "from app.models.recommendation import Recommendation; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/recommendation.py
git commit -m "model: add agent_opportunity_json, linked_step_ids, domain_id, financial_evaluation_status"
```

---

### Task 3: Domain Context Assembler (Phase 1)

**Files:**
- Create: `backend/app/services/recommendations/domain_assembler.py`
- Create: `backend/tests/services/recommendations/__init__.py`
- Create: `backend/tests/services/recommendations/test_domain_assembler.py`

- [ ] **Step 1: Write failing tests for domain context assembly helpers**

Create `backend/tests/services/recommendations/__init__.py` (empty file).

Create `backend/tests/services/recommendations/test_domain_assembler.py`:

```python
"""Tests for domain context assembly (Phase 1) — pure logic, no DB."""

import pytest
from uuid import uuid4

from app.services.recommendations.domain_assembler import (
    build_actor_roster,
    build_touchpoint_inventory,
    serialize_domain_context,
    truncate_steps_for_token_budget,
)


def _fake_process(name, actors=None, touchpoints=None, steps=None):
    return {
        "id": str(uuid4()),
        "name": name,
        "level": "process",
        "description": f"Description of {name}",
        "narrative": None,
        "actors": actors or [],
        "trigger_conditions": [],
        "decision_logic": [],
        "system_touchpoints": touchpoints or [],
        "failure_modes": [],
        "value_classification": "BVA",
        "complexity_score": "medium",
        "automation_potential": "high",
        "estimated_duration": None,
        "estimated_frequency": None,
        "steps": steps or [],
    }


def _fake_step(name, actors=None, touchpoints=None):
    return {
        "id": str(uuid4()),
        "name": name,
        "level": "step",
        "actors": actors or [],
        "decision_logic": [],
        "trigger_conditions": [],
        "system_touchpoints": touchpoints or [],
        "failure_modes": [],
        "estimated_duration": "15min",
        "estimated_frequency": "daily",
        "sequencing": {},
        "value_classification": "NVA",
        "complexity_score": "low",
    }


class TestBuildActorRoster:
    def test_deduplicates_across_processes(self):
        procs = [
            _fake_process("Proc A", actors=["Sales Rep", "Manager"]),
            _fake_process("Proc B", actors=["Sales Rep", "Analyst"]),
        ]
        roster = build_actor_roster(procs)
        assert "Sales Rep" in roster
        assert len(roster["Sales Rep"]) == 2
        assert "Manager" in roster
        assert "Analyst" in roster

    def test_includes_step_level_actors(self):
        step = _fake_step("Step 1", actors=["Intern"])
        procs = [_fake_process("Proc A", actors=["Manager"], steps=[step])]
        roster = build_actor_roster(procs)
        assert "Intern" in roster
        assert "Proc A > Step 1" in roster["Intern"][0]

    def test_empty_actors(self):
        procs = [_fake_process("Proc A")]
        roster = build_actor_roster(procs)
        assert roster == {}


class TestBuildTouchpointInventory:
    def test_groups_by_object(self):
        procs = [
            _fake_process("Proc A", touchpoints=[
                "Lead.Status", "Lead.Rating", "Opportunity.StageName",
            ]),
        ]
        inventory = build_touchpoint_inventory(procs)
        assert "Lead" in inventory
        assert "Status" in inventory["Lead"]
        assert "Rating" in inventory["Lead"]
        assert "Opportunity" in inventory

    def test_handles_non_dotted_touchpoints(self):
        procs = [_fake_process("Proc A", touchpoints=["SomeSystem"])]
        inventory = build_touchpoint_inventory(procs)
        assert "SomeSystem" in inventory


class TestTruncateSteps:
    def test_keeps_all_when_under_limit(self):
        steps = [_fake_step(f"Step {i}") for i in range(5)]
        result = truncate_steps_for_token_budget(steps, max_steps=8)
        assert len(result) == 5

    def test_truncates_to_max(self):
        steps = [_fake_step(f"Step {i}") for i in range(12)]
        result = truncate_steps_for_token_budget(steps, max_steps=8)
        assert len(result) == 8


class TestSerializeDomainContext:
    def test_returns_complete_structure(self):
        domain = {"id": str(uuid4()), "name": "Sales Ops", "description": "desc", "narrative": None}
        procs = [_fake_process("Lead Qual", actors=["Rep"], touchpoints=["Lead.Status"])]
        handoffs = []
        result = serialize_domain_context(domain, procs, handoffs)
        assert result["domain"]["name"] == "Sales Ops"
        assert len(result["processes"]) == 1
        assert "actor_roster" in result
        assert "system_touchpoints_summary" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/recommendations/test_domain_assembler.py -v`
Expected: FAIL — `domain_assembler` module doesn't exist yet.

- [ ] **Step 3: Implement domain_assembler.py**

Create `backend/app/services/recommendations/domain_assembler.py`:

```python
"""Phase 1: Domain context assembly from discovery data.

Pure Python + SQL. No LLM calls. Assembles a structured context document
per domain for the agent opportunity analysis in Phase 2.
"""
from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess

logger = logging.getLogger(__name__)

MAX_STEPS_PER_PROCESS = 8


def _extract_actors(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("role") or str(item)
                out.append(str(name))
        return out
    return [str(raw)]


def _extract_touchpoint_strings(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                obj = item.get("object", "")
                field = item.get("field", "")
                if obj and field:
                    out.append(f"{obj}.{field}")
                elif obj:
                    out.append(str(obj))
                else:
                    out.append(json.dumps(item, default=str))
            else:
                out.append(str(item))
        return out
    return [str(raw)]


def build_actor_roster(processes: list[dict]) -> dict[str, list[str]]:
    roster: dict[str, list[str]] = defaultdict(list)
    for proc in processes:
        proc_name = proc.get("name", "?")
        for actor in _extract_actors(proc.get("actors")):
            roster[actor].append(proc_name)
        for step in proc.get("steps", []):
            step_name = step.get("name", "?")
            for actor in _extract_actors(step.get("actors")):
                roster[actor].append(f"{proc_name} > {step_name}")
    return {k: v for k, v in roster.items() if v}


def build_touchpoint_inventory(processes: list[dict]) -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = defaultdict(list)
    for proc in processes:
        for tp in _extract_touchpoint_strings(proc.get("system_touchpoints")):
            if "." in tp:
                obj, field = tp.split(".", 1)
                if field not in inventory[obj]:
                    inventory[obj].append(field)
            else:
                if tp not in inventory:
                    inventory[tp] = []
        for step in proc.get("steps", []):
            for tp in _extract_touchpoint_strings(step.get("system_touchpoints")):
                if "." in tp:
                    obj, field = tp.split(".", 1)
                    if field not in inventory[obj]:
                        inventory[obj].append(field)
                else:
                    if tp not in inventory:
                        inventory[tp] = []
    return dict(inventory)


def truncate_steps_for_token_budget(
    steps: list[dict], max_steps: int = MAX_STEPS_PER_PROCESS
) -> list[dict]:
    if len(steps) <= max_steps:
        return steps
    complexity_order = {"high": 0, "medium": 1, "low": 2, None: 1}
    ranked = sorted(
        steps,
        key=lambda s: complexity_order.get(
            (s.get("complexity_score") or "").lower() or None, 1
        ),
    )
    return ranked[:max_steps]


def _process_to_context(proc: BusinessProcess, children: list[BusinessProcess]) -> dict:
    steps_raw = []
    for child in children:
        steps_raw.append({
            "id": str(child.id),
            "name": child.name,
            "level": child.level,
            "actors": list(child.actors) if child.actors else [],
            "decision_logic": list(child.decision_logic) if child.decision_logic else [],
            "trigger_conditions": list(child.trigger_conditions) if child.trigger_conditions else [],
            "system_touchpoints": list(child.system_touchpoints) if child.system_touchpoints else [],
            "failure_modes": list(child.failure_modes) if child.failure_modes else [],
            "estimated_duration": child.estimated_duration,
            "estimated_frequency": child.estimated_frequency,
            "sequencing": dict(child.sequencing) if child.sequencing else {},
            "value_classification": child.value_classification,
            "complexity_score": child.complexity_score,
        })

    steps_truncated = truncate_steps_for_token_budget(steps_raw)

    return {
        "id": str(proc.id),
        "name": proc.name,
        "level": proc.level,
        "description": proc.description,
        "narrative": proc.narrative,
        "actors": list(proc.actors) if proc.actors else [],
        "trigger_conditions": list(proc.trigger_conditions) if proc.trigger_conditions else [],
        "decision_logic": list(proc.decision_logic) if proc.decision_logic else [],
        "system_touchpoints": list(proc.system_touchpoints) if proc.system_touchpoints else [],
        "failure_modes": list(proc.failure_modes) if proc.failure_modes else [],
        "value_classification": proc.value_classification,
        "complexity_score": proc.complexity_score,
        "automation_potential": proc.automation_potential,
        "estimated_duration": proc.estimated_duration,
        "estimated_frequency": proc.estimated_frequency,
        "steps": steps_truncated,
    }


def serialize_domain_context(
    domain: dict,
    processes: list[dict],
    handoffs: list[dict],
) -> dict:
    return {
        "domain": domain,
        "processes": processes,
        "handoffs": handoffs,
        "actor_roster": build_actor_roster(processes),
        "system_touchpoints_summary": build_touchpoint_inventory(processes),
    }


async def assemble_domain_contexts(
    org_id: UUID, db: AsyncSession
) -> list[dict]:
    """Assemble domain context documents for all domains in the latest discovery run.

    Returns a list of serialized domain context dicts, one per domain.
    Process order within each domain is randomized to mitigate LLM position bias.
    """
    run_res = await db.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.org_id == org_id, DiscoveryRun.status == "completed")
        .order_by(DiscoveryRun.completed_at.desc().nulls_last())
        .limit(1)
    )
    run = run_res.scalar_one_or_none()
    if run is None:
        return []

    all_procs_res = await db.execute(
        select(BusinessProcess)
        .where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run.id,
        )
        .options(selectinload(BusinessProcess.parent))
    )
    all_procs = all_procs_res.scalars().unique().all()

    domains = [p for p in all_procs if p.level == "domain"]
    procs_by_parent: dict[UUID, list[BusinessProcess]] = defaultdict(list)
    for p in all_procs:
        if p.parent_id is not None:
            procs_by_parent[p.parent_id].append(p)

    handoff_res = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == run.id,
        )
    )
    all_handoffs = handoff_res.scalars().all()

    domain_proc_ids: dict[UUID, set[UUID]] = {}

    contexts: list[dict] = []
    for domain in domains:
        domain_dict = {
            "id": str(domain.id),
            "name": domain.name,
            "description": domain.description,
            "narrative": domain.narrative,
        }

        child_procs = procs_by_parent.get(domain.id, [])
        process_level = [p for p in child_procs if p.level in ("process", "subprocess")]

        proc_contexts = []
        all_ids_in_domain: set[UUID] = {domain.id}
        for proc in process_level:
            all_ids_in_domain.add(proc.id)
            children = procs_by_parent.get(proc.id, [])
            for c in children:
                all_ids_in_domain.add(c.id)
            proc_contexts.append(_process_to_context(proc, children))

        random.shuffle(proc_contexts)

        domain_proc_ids[domain.id] = all_ids_in_domain

        domain_handoffs = []
        for h in all_handoffs:
            if h.source_process_id in all_ids_in_domain or h.target_process_id in all_ids_in_domain:
                src_name = next(
                    (p.name for p in all_procs if p.id == h.source_process_id), str(h.source_process_id)
                )
                tgt_name = next(
                    (p.name for p in all_procs if p.id == h.target_process_id), str(h.target_process_id)
                )
                domain_handoffs.append({
                    "source_process": src_name,
                    "target_process": tgt_name,
                    "handoff_type": h.handoff_type,
                    "is_gap": h.is_gap,
                    "description": h.description,
                })

        ctx = serialize_domain_context(domain_dict, proc_contexts, domain_handoffs)
        ctx["_discovery_run_id"] = str(run.id)
        ctx["_domain_db_id"] = str(domain.id)
        contexts.append(ctx)

    return contexts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/recommendations/test_domain_assembler.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendations/domain_assembler.py \
        backend/tests/services/recommendations/__init__.py \
        backend/tests/services/recommendations/test_domain_assembler.py
git commit -m "feat: add domain context assembler (Phase 1)"
```

---

### Task 4: Prompt Blocks and Operation Configs

**Files:**
- Modify: `backend/app/services/prompts/seeds.py`
- Modify: `backend/app/services/ai/operations.py`

- [ ] **Step 1: Add agent opportunity prompt blocks to seeds.py**

Add after the existing `_RECOMMENDATIONS_COMPOSITE_PROTOCOL` block (around line 435):

```python
# --- Agent opportunity analysis (domain-level) ---

_AGENT_OPPORTUNITY_INSTRUCTIONS = """You are an Agentforce solution architect analyzing a business domain to identify where Salesforce Agentforce agents can replace or augment existing manual processes.

You will receive a complete domain context: all processes, their steps, actors, decision logic, system touchpoints, handoffs, and failure modes. Your job is to identify agent opportunities — coherent clusters of work that a single Agentforce agent could own across multiple processes and steps.

AGENTFORCE AGENT CAPABILITIES:

An Agentforce agent can:
- Own multiple "topics" (distinct jobs) — each topic has its own actions and reasoning
- Route between topics based on user input or data conditions
- Execute deterministic logic (if/then, field updates, record queries) before LLM reasoning
- Use LLM reasoning for judgment calls: classification, prioritization, content generation, exception handling, contextual decision-making
- Call Apex actions (database queries, API callouts, complex business logic)
- Call Flow actions (record operations, simple automations)
- Carry mutable state across topics via global variables
- Operate conversationally (user-facing) OR headlessly (triggered by record events or Flows, fully autonomous)
- Handle structured data (Salesforce records) and unstructured data (emails, free text, case descriptions)
- Gate topic availability behind conditions (authentication, data loaded, role checks)
- Pre-load data deterministically before the LLM reasons
- Support Bring Your Own Model via Einstein Studio (Azure, Google, AWS, OpenAI models)

An agent CANNOT:
- Call external APIs directly — any integration outside Salesforce needs Apex middleware
- Run long-duration background processes (agents are request-response per turn)
- Process files or documents natively (needs Apex for parsing)
- Replace complex multi-org or multi-cloud orchestration
- Maintain state between separate sessions (state is per-session only)

PLATFORM LIMITS: Agentforce has per-org and per-agent limits on topics and actions (varies by edition). Design agents with 3-6 topics each as best practice. Standard Apex governor limits apply to all actions.

AGENT DESIGN PRINCIPLES:

1. ONE AGENT = ONE DOMAIN OF RESPONSIBILITY — not a single task. Think "Sales Qualification Agent" not "BANT Scoring Agent."
2. TOPICS = JOBS WITHIN THAT RESPONSIBILITY — 3-6 topics is typical.
3. GROUP BY SHARED CONTEXT, NOT PROCESS BOUNDARIES — look for shared data objects, same actor/role, similar decision patterns, sequential handoffs an agent could eliminate.
4. HEADLESS WHEN NO HUMAN INPUT NEEDED — if triggered by data events with no user interaction, it's headless.
5. DETERMINISTIC CORE + AGENTIC EDGE CASES — deterministic handles the predictable 80%, LLM handles ambiguity and exceptions.
6. FLAG INTEGRATION REQUIREMENTS HONESTLY — every external system needs Apex middleware."""

_AGENT_OPPORTUNITY_PROTOCOL = """ANTIPATTERNS — DO NOT RECOMMEND THESE:
- ONE AGENT PER PROCESS STEP — a single step is a topic at most, never a standalone agent
- PURELY DETERMINISTIC AGENTS — if every topic is just if/then with no LLM reasoning, recommend a Flow, not an agent
- NOTIFICATION-ONLY AGENTS — agents that only send emails/tasks without making decisions are automation rules, not agents
- BOIL-THE-OCEAN AGENTS — don't propose one mega-agent per domain. Find 2-4 focused agents.
- OVERLOADED AGENTS — if scope exceeds what a single agent can hold, split into multiple focused agents

Return ONLY valid JSON with this exact shape:

{
  "agent_opportunities": [
    {
      "agent_name": "Descriptive name for the proposed agent",
      "agent_type": "headless" | "conversational" | "hybrid",
      "description": "2-3 sentences: what this agent does, who it serves, what business outcome it drives",
      "topics": [
        {
          "topic_name": "Name for this topic/job",
          "description": "What this topic handles",
          "reasoning_type": "deterministic" | "agentic" | "hybrid",
          "actions_needed": ["List of actions/tools this topic would call"]
        }
      ],
      "replaces": [
        {
          "process_id": "uuid from the input",
          "process_name": "string",
          "steps_replaced": ["step names from the input"],
          "step_ids": ["step uuids from the input"],
          "replacement_type": "full" | "partial"
        }
      ],
      "trigger": "What kicks this agent off",
      "data_requirements": ["Salesforce objects this agent needs"],
      "integration_points": ["External systems needing Apex middleware"],
      "complexity_estimate": "low" | "medium" | "high",
      "confidence": 0.0-1.0,
      "rationale": "Why these processes/steps belong together and why an agent (not a Flow) is right",
      "risks": "Key implementation risks or feasibility concerns",
      "financial_signals": {
        "actors_impacted": ["role names"],
        "estimated_hours_per_week_saved": number,
        "estimated_frequency": "daily" | "weekly" | "monthly" | "ad-hoc",
        "estimated_actor_count": number,
        "primary_role_type": "dominant role for salary estimation"
      }
    }
  ],
  "uncovered_processes": [
    {
      "process_name": "string",
      "reason": "Why not included in any agent opportunity"
    }
  ]
}

Rules:
- process_id and step_ids must be valid UUIDs from the domain context input
- Every process in the domain should appear in either an agent opportunity's replaces array OR in uncovered_processes
- confidence should reflect genuine assessment — not all 0.80
- financial_signals must be internally consistent with the processes replaced"""

# --- Agent opportunity cross-domain synthesis ---

_AGENT_OPPORTUNITY_CROSS_DOMAIN_INSTRUCTIONS = """You are analyzing agent opportunities identified across multiple business domains to find cross-domain opportunities.

Look for:
1. Cross-domain agents: the same actor/role doing similar work in different domains
2. Handoff bridge agents: cross-domain handoff gaps where an agent could bridge the boundary
3. Merge candidates: similar agent opportunities in different domains that should be one agent"""

_AGENT_OPPORTUNITY_CROSS_DOMAIN_PROTOCOL = """Return ONLY valid JSON with this shape:

{
  "cross_domain_opportunities": [
    {
      "agent_name": "string",
      "agent_type": "headless" | "conversational" | "hybrid",
      "description": "What this cross-domain agent does",
      "topics": [{"topic_name": "string", "description": "string", "reasoning_type": "string", "actions_needed": ["string"]}],
      "replaces": [{"process_id": "uuid", "process_name": "string", "steps_replaced": ["string"], "step_ids": ["uuid"], "replacement_type": "full" | "partial"}],
      "source_domains": ["domain names this spans"],
      "trigger": "string",
      "data_requirements": ["string"],
      "integration_points": ["string"],
      "complexity_estimate": "low" | "medium" | "high",
      "confidence": 0.0-1.0,
      "rationale": "string",
      "risks": "string",
      "financial_signals": {"actors_impacted": ["string"], "estimated_hours_per_week_saved": 0, "estimated_frequency": "string", "estimated_actor_count": 0, "primary_role_type": "string"}
    }
  ],
  "merge_suggestions": [
    {
      "agent_a": "agent name from domain A",
      "agent_b": "agent name from domain B",
      "reason": "Why these should be merged into one agent"
    }
  ]
}

If no cross-domain opportunities exist, return empty arrays."""
```

Then register these blocks in the `SEED_BLOCKS` dict (or whatever mechanism `seeds.py` uses to register prompt blocks). Look for the pattern used by `_RECOMMENDATIONS_INSTRUCTIONS` and follow it exactly.

- [ ] **Step 2: Add operation configs to operations.py**

Add after the existing `chat_recommendation` block (around line 184):

```python
    "agent_opportunity": {
        "model": "anthropic/claude-sonnet-4-6",
        "tier": "strong",
        "thinking_budget": 16000,
        "output_format": "json",
        "label": "Agent Opportunity Analysis",
        "group": "synthesis",
        "description": "Domain-level analysis identifying Agentforce agent opportunities across processes and steps.",
    },
    "agent_opportunity_cross_domain": {
        "model": "anthropic/claude-sonnet-4-6",
        "tier": "strong",
        "thinking_budget": 8000,
        "output_format": "json",
        "label": "Cross-Domain Agent Synthesis",
        "group": "synthesis",
        "description": "Identifies agent opportunities spanning multiple business domains.",
    },
```

- [ ] **Step 3: Verify imports work**

Run: `cd backend && python -c "from app.services.ai.operations import OPERATIONS; print('agent_opportunity' in OPERATIONS)"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/prompts/seeds.py backend/app/services/ai/operations.py
git commit -m "feat: add agent opportunity prompt blocks and operation configs"
```

---

### Task 5: Agent Analyzer (Phase 2)

**Files:**
- Create: `backend/app/services/recommendations/agent_analyzer.py`
- Create: `backend/tests/services/recommendations/test_agent_analyzer.py`

- [ ] **Step 1: Write failing tests for output parsing and ID resolution**

Create `backend/tests/services/recommendations/test_agent_analyzer.py`:

```python
"""Tests for agent analyzer — output parsing, ID resolution, validation."""

import pytest
from uuid import uuid4

from app.services.recommendations.agent_analyzer import (
    parse_opportunity_response,
    resolve_ids,
    validate_opportunity,
)


SAMPLE_DOMAIN_CONTEXT = {
    "domain": {"id": str(uuid4()), "name": "Sales Ops"},
    "processes": [
        {
            "id": "aaaa-1111",
            "name": "Lead Qualification",
            "steps": [
                {"id": "bbbb-1111", "name": "BANT Scoring"},
                {"id": "bbbb-2222", "name": "Lead Rating"},
            ],
        },
        {
            "id": "aaaa-2222",
            "name": "Opportunity Creation",
            "steps": [
                {"id": "cccc-1111", "name": "Record Setup"},
            ],
        },
    ],
}


def _valid_opportunity():
    return {
        "agent_name": "Test Agent",
        "agent_type": "headless",
        "description": "Does stuff",
        "topics": [{"topic_name": "T1", "description": "d", "reasoning_type": "agentic", "actions_needed": []}],
        "replaces": [
            {
                "process_id": "aaaa-1111",
                "process_name": "Lead Qualification",
                "steps_replaced": ["BANT Scoring"],
                "step_ids": ["bbbb-1111"],
                "replacement_type": "partial",
            }
        ],
        "trigger": "Record event",
        "data_requirements": ["Lead"],
        "integration_points": [],
        "complexity_estimate": "medium",
        "confidence": 0.8,
        "rationale": "Good fit",
        "risks": "None",
        "financial_signals": {
            "actors_impacted": ["Rep"],
            "estimated_hours_per_week_saved": 5,
            "estimated_frequency": "daily",
            "estimated_actor_count": 2,
            "primary_role_type": "sales_operations",
        },
    }


class TestParseOpportunityResponse:
    def test_parses_valid_json(self):
        raw = {"agent_opportunities": [_valid_opportunity()], "uncovered_processes": []}
        result = parse_opportunity_response(raw)
        assert len(result["agent_opportunities"]) == 1

    def test_handles_missing_uncovered(self):
        raw = {"agent_opportunities": [_valid_opportunity()]}
        result = parse_opportunity_response(raw)
        assert result["uncovered_processes"] == []

    def test_filters_invalid_opportunities(self):
        bad = {"agent_name": "", "topics": []}
        raw = {"agent_opportunities": [_valid_opportunity(), bad]}
        result = parse_opportunity_response(raw)
        assert len(result["agent_opportunities"]) == 1


class TestValidateOpportunity:
    def test_valid_passes(self):
        assert validate_opportunity(_valid_opportunity()) is True

    def test_missing_name_fails(self):
        opp = _valid_opportunity()
        opp["agent_name"] = ""
        assert validate_opportunity(opp) is False

    def test_no_topics_fails(self):
        opp = _valid_opportunity()
        opp["topics"] = []
        assert validate_opportunity(opp) is False

    def test_no_replaces_fails(self):
        opp = _valid_opportunity()
        opp["replaces"] = []
        assert validate_opportunity(opp) is False


class TestResolveIds:
    def test_resolves_by_name_match(self):
        opp = _valid_opportunity()
        resolved = resolve_ids(opp, SAMPLE_DOMAIN_CONTEXT)
        replaces = resolved["replaces"][0]
        assert replaces["process_id"] == "aaaa-1111"
        assert "bbbb-1111" in replaces["step_ids"]

    def test_handles_unresolvable_step(self):
        opp = _valid_opportunity()
        opp["replaces"][0]["steps_replaced"] = ["Nonexistent Step"]
        opp["replaces"][0]["step_ids"] = []
        resolved = resolve_ids(opp, SAMPLE_DOMAIN_CONTEXT)
        assert resolved["replaces"][0]["step_ids"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/recommendations/test_agent_analyzer.py -v`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Implement agent_analyzer.py**

Create `backend/app/services/recommendations/agent_analyzer.py`:

```python
"""Phase 2: LLM-driven agent opportunity analysis per domain."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)


def validate_opportunity(opp: dict) -> bool:
    if not (opp.get("agent_name") or "").strip():
        return False
    if not opp.get("topics"):
        return False
    if not opp.get("replaces"):
        return False
    return True


def parse_opportunity_response(raw: dict | list) -> dict:
    if isinstance(raw, list):
        raw = {"agent_opportunities": raw, "uncovered_processes": []}
    opportunities = raw.get("agent_opportunities") or raw.get("opportunities") or []
    uncovered = raw.get("uncovered_processes") or []
    valid = [o for o in opportunities if isinstance(o, dict) and validate_opportunity(o)]
    return {"agent_opportunities": valid, "uncovered_processes": uncovered}


def resolve_ids(opportunity: dict, domain_context: dict) -> dict:
    proc_name_to_id: dict[str, str] = {}
    proc_step_map: dict[str, dict[str, str]] = {}

    for proc in domain_context.get("processes", []):
        pid = proc.get("id", "")
        pname = proc.get("name", "")
        proc_name_to_id[pname.lower()] = pid
        step_map: dict[str, str] = {}
        for step in proc.get("steps", []):
            sname = step.get("name", "")
            sid = step.get("id", "")
            step_map[sname.lower()] = sid
        proc_step_map[pid] = step_map

    for rep in opportunity.get("replaces", []):
        pname = (rep.get("process_name") or "").lower()
        if pname in proc_name_to_id:
            rep["process_id"] = proc_name_to_id[pname]

        pid = rep.get("process_id", "")
        steps = proc_step_map.get(pid, {})
        resolved_step_ids = []
        for sname in rep.get("steps_replaced", []):
            sid = steps.get(sname.lower())
            if sid:
                resolved_step_ids.append(sid)
        rep["step_ids"] = resolved_step_ids

    return opportunity


def _build_prompt(domain_context_json: str, blocks: dict[str, str]) -> str:
    instructions = blocks.get("instructions", "")
    protocol = blocks.get("protocol", "")
    return f"""{instructions}

## Domain Context

{domain_context_json}

{protocol}"""


async def analyze_domain(
    domain_context: dict,
    org_id: UUID,
    db: AsyncSession,
    *,
    cancel_check: Callable | None = None,
    heartbeat: Callable | None = None,
) -> dict:
    """Run Phase 2 agent opportunity analysis for a single domain.

    Returns parsed and ID-resolved opportunity response dict.
    """
    from app.services.ai.router import llm_call, parse_json_response

    blocks = await resolve_prompt_blocks("agent_opportunity", org_id, db)

    ctx_for_llm = {k: v for k, v in domain_context.items() if not k.startswith("_")}
    domain_json = json.dumps(ctx_for_llm, indent=2, default=str)

    prompt = _build_prompt(domain_json, blocks)

    if cancel_check:
        await cancel_check()

    try:
        result = llm_call(
            prompt=prompt,
            max_tokens=16000,
            tier="strong",
            operation="agent_opportunity",
        )
        data = parse_json_response(result.text)
    except Exception:
        logger.exception("agent_analysis_failed domain=%s org=%s",
                         domain_context.get("domain", {}).get("name"), org_id)
        return {"agent_opportunities": [], "uncovered_processes": []}

    if heartbeat:
        await heartbeat()

    parsed = parse_opportunity_response(data)

    for opp in parsed["agent_opportunities"]:
        resolve_ids(opp, domain_context)

    return parsed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/recommendations/test_agent_analyzer.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendations/agent_analyzer.py \
        backend/tests/services/recommendations/test_agent_analyzer.py
git commit -m "feat: add agent analyzer with output parsing and ID resolution (Phase 2)"
```

---

### Task 6: Cross-Domain Synthesis (Phase 3)

**Files:**
- Create: `backend/app/services/recommendations/cross_domain.py`

- [ ] **Step 1: Implement cross_domain.py**

```python
"""Phase 3: Cross-domain agent opportunity synthesis."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import ProcessHandoff
from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)


def _summarize_opportunities(all_domain_results: list[dict]) -> list[dict]:
    summaries = []
    for domain_result in all_domain_results:
        domain_name = domain_result.get("_domain_name", "Unknown")
        for opp in domain_result.get("agent_opportunities", []):
            summaries.append({
                "domain": domain_name,
                "agent_name": opp.get("agent_name"),
                "agent_type": opp.get("agent_type"),
                "description": opp.get("description"),
                "topics": [t.get("topic_name") for t in opp.get("topics", [])],
                "actors_impacted": (opp.get("financial_signals") or {}).get("actors_impacted", []),
                "data_requirements": opp.get("data_requirements", []),
                "integration_points": opp.get("integration_points", []),
            })
    return summaries


async def synthesize_cross_domain(
    all_domain_results: list[dict],
    org_id: UUID,
    discovery_run_id: UUID,
    db: AsyncSession,
) -> dict:
    """Run Phase 3: identify cross-domain agent opportunities.

    Returns dict with cross_domain_opportunities and merge_suggestions.
    """
    if len(all_domain_results) < 2:
        return {"cross_domain_opportunities": [], "merge_suggestions": []}

    from app.services.ai.router import llm_call, parse_json_response

    summaries = _summarize_opportunities(all_domain_results)
    if not summaries:
        return {"cross_domain_opportunities": [], "merge_suggestions": []}

    ho_res = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == discovery_run_id,
        )
    )
    all_handoffs = ho_res.scalars().all()
    cross_domain_handoffs = []
    domain_proc_ids: dict[str, set[str]] = {}
    for dr in all_domain_results:
        dname = dr.get("_domain_name", "")
        ids = set()
        for p in dr.get("_processes_raw", []):
            ids.add(str(p.get("id", "")))
        domain_proc_ids[dname] = ids

    all_domain_ids = set()
    for ids in domain_proc_ids.values():
        all_domain_ids |= ids

    for h in all_handoffs:
        src = str(h.source_process_id)
        tgt = str(h.target_process_id)
        src_domain = None
        tgt_domain = None
        for dname, ids in domain_proc_ids.items():
            if src in ids:
                src_domain = dname
            if tgt in ids:
                tgt_domain = dname
        if src_domain and tgt_domain and src_domain != tgt_domain:
            cross_domain_handoffs.append({
                "source_domain": src_domain,
                "target_domain": tgt_domain,
                "description": h.description,
                "is_gap": h.is_gap,
                "handoff_type": h.handoff_type,
            })

    blocks = await resolve_prompt_blocks("agent_opportunity_cross_domain", org_id, db)
    instructions = blocks.get("instructions", "")
    protocol = blocks.get("protocol", "")

    prompt = f"""{instructions}

## Agent Opportunities by Domain

{json.dumps(summaries, indent=2, default=str)}

## Cross-Domain Handoffs

{json.dumps(cross_domain_handoffs, indent=2, default=str)}

{protocol}"""

    try:
        result = llm_call(
            prompt=prompt,
            max_tokens=8192,
            tier="strong",
            operation="agent_opportunity_cross_domain",
        )
        data = parse_json_response(result.text)
    except Exception:
        logger.exception("cross_domain_synthesis_failed org=%s", org_id)
        return {"cross_domain_opportunities": [], "merge_suggestions": []}

    if isinstance(data, list):
        data = {"cross_domain_opportunities": data, "merge_suggestions": []}

    return {
        "cross_domain_opportunities": data.get("cross_domain_opportunities") or [],
        "merge_suggestions": data.get("merge_suggestions") or [],
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/recommendations/cross_domain.py
git commit -m "feat: add cross-domain synthesis module (Phase 3)"
```

---

### Task 7: Rewrite Pipeline Orchestration

**Files:**
- Modify: `backend/app/services/recommendations/pipeline.py`

- [ ] **Step 1: Rewrite pipeline.py**

Replace the entire contents of `backend/app/services/recommendations/pipeline.py` with the new 4-phase orchestration. The new pipeline:

1. Reuses the existing `RecommendationRun` creation, cancellation, and heartbeat patterns from the current file
2. Calls `assemble_domain_contexts` (Phase 1) instead of `generate_discovered_candidates` / `generate_synthesized_candidates`
3. Calls `analyze_domain` (Phase 2) per domain instead of `score_candidates_with_llm`
4. Calls `synthesize_cross_domain` (Phase 3) when 2+ domains have opportunities
5. Builds `Recommendation` rows from opportunity cards instead of scored candidates
6. Sets `financial_evaluation_status = "pending"` on all rows
7. Enqueues `evaluate_agent_financials_task` after committing

Key changes to `_build_recommendation`:
- `recommendation_type` = `"agent_opportunity"` or `"cross_domain"`
- `agent_opportunity_json` = the full opportunity card
- `linked_process_ids` = all process IDs from `replaces`
- `linked_step_ids` = all step IDs from `replaces`
- `domain_id` = the domain's BusinessProcess UUID
- `composite_score` = the `confidence` value from the LLM
- `automation_type` = derived from mix of topic `reasoning_type` values
- `financial_evaluation_status` = `"pending"`
- No `base_score`, `llm_score`, or `score_divergence_flag`
- `assumptions_json` stays empty (filled by Phase 4)
- `scenarios_json` stays empty (filled by Phase 4)

The `_build_recommendation` function should handle both Phase 2 (per-domain) and Phase 3 (cross-domain) opportunities via the same code path.

Preserve the existing patterns: `PipelineCancelled` exception, `_check_cancelled`, `_update_run_progress`, `_heartbeat`, `stage_results` tracking, delete-before-insert of previous pipeline recs, batch commit every 5 rows.

After all recs are committed, enqueue the financial evaluation:

```python
from app.workers.analysis import evaluate_agent_financials_task
evaluate_agent_financials_task.delay(str(org_id), str(run_id))
```

- [ ] **Step 2: Verify the module imports correctly**

Run: `cd backend && python -c "from app.services.recommendations.pipeline import run_recommendation_pipeline; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendations/pipeline.py
git commit -m "feat: rewrite pipeline with 4-phase agent opportunity orchestration"
```

---

### Task 8: Financial Evaluation Celery Task (Phase 4)

**Files:**
- Modify: `backend/app/workers/analysis.py`

- [ ] **Step 1: Add the evaluate_agent_financials_task**

Add after the existing `generate_recommendations_task` in `backend/app/workers/analysis.py`:

```python
@celery_app.task(name="recommendations.evaluate_agent_financials")
def evaluate_agent_financials_task(org_id: str, run_id: str) -> str:
    """Async financial evaluation for agent opportunities (Phase 4).

    Reads financial_signals from each pending recommendation, assembles
    assumptions, runs compute_projections, writes back results.
    """
    import asyncio

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span
    from app.services.recommendations.financial_engine import compute_projections

    ROLE_SALARY = {
        "sales_operations": 70000,
        "account_executive": 110000,
        "engineering": 130000,
        "customer_support": 55000,
        "finance_operations": 80000,
        "marketing": 90000,
        "operations": 75000,
    }
    COMPLEXITY_TECH_COST = {"low": 8000, "medium": 18000, "high": 35000}
    INTEGRATION_COST_PER = 5000

    def _build_assumptions(opp_json: dict) -> dict | None:
        signals = opp_json.get("financial_signals")
        if not isinstance(signals, dict):
            return None
        hours = signals.get("estimated_hours_per_week_saved")
        if not hours or float(hours) <= 0:
            return None

        role = signals.get("primary_role_type", "operations").lower()
        fte_cost = ROLE_SALARY.get(role, 75000)
        actor_count = int(signals.get("estimated_actor_count", 1))
        complexity = (opp_json.get("complexity_estimate") or "medium").lower()
        integrations = len(opp_json.get("integration_points") or [])
        tech_cost = COMPLEXITY_TECH_COST.get(complexity, 18000) + (integrations * INTEGRATION_COST_PER)

        topics = opp_json.get("topics") or []
        has_agentic = any(t.get("reasoning_type") in ("agentic", "hybrid") for t in topics)
        estimated_actions_per_invocation = max(len(topics) * 3, 5)
        frequency = (signals.get("estimated_frequency") or "daily").lower()
        invocations_per_month = {"daily": 22, "weekly": 4, "monthly": 1, "ad-hoc": 8}.get(frequency, 10)
        annual_op_cost = (
            estimated_actions_per_invocation * 0.10 * invocations_per_month * 12 * actor_count
            if has_agentic else 2000
        )

        return {
            "fte_annual_cost": fte_cost,
            "hours_per_week": float(hours),
            "frequency": frequency,
            "actor_count": actor_count,
            "role_type": role,
            "technology_cost": tech_cost,
            "change_management_factor": 0.35,
            "annual_operational_cost": round(annual_op_cost, 2),
            "adoption_ramp": [0.1, 0.5, 0.85, 0.95, 1.0],
            "productivity_dip": 0.10,
            "efficiency_gain": 0.65,
            "hard_savings_pct": 0.25,
            "discount_rate": 0.10,
            "source": "auto_estimated",
            "overrides": {},
        }

    async def _run() -> str:
        from decimal import Decimal

        from sqlalchemy import select, update
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.recommendation import Recommendation

        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(_engine, expire_on_commit=False)
            async with factory() as session:
                q = await session.execute(
                    select(Recommendation).where(
                        Recommendation.org_id == UUID(org_id),
                        Recommendation.recommendation_run_id == UUID(run_id),
                        Recommendation.financial_evaluation_status == "pending",
                    )
                )
                recs = list(q.scalars().all())
                evaluated = 0
                for rec in recs:
                    try:
                        opp = rec.agent_opportunity_json or {}
                        assumptions = _build_assumptions(opp)
                        if assumptions is None:
                            rec.financial_evaluation_status = "failed"
                            continue
                        automation_type = rec.automation_type or "hybrid"
                        projections = compute_projections(assumptions, automation_type=automation_type)
                        rec.assumptions_json = assumptions
                        rec.scenarios_json = projections
                        rec.estimated_roi = Decimal(str(projections["npv"]["expected"]))
                        rec.financial_evaluation_status = "completed"
                        evaluated += 1
                    except Exception as exc:
                        logger.exception("financial_eval_failed rec=%s", rec.id)
                        rec.financial_evaluation_status = "failed"
                    if evaluated % 5 == 0:
                        await session.commit()
                await session.commit()
                return f"evaluated={evaluated} total={len(recs)}"
        finally:
            await _engine.dispose()

    import logging
    logger = logging.getLogger(__name__)
    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("financial_evaluation", metadata={"org_id": org_id, "run_id": run_id}):
                result = asyncio.run(_run())
        return result
    finally:
        flush_langfuse()
```

Also add the UUID import at the top of the file:

```python
from uuid import UUID
```

- [ ] **Step 2: Verify the task registers**

Run: `cd backend && python -c "from app.workers.analysis import evaluate_agent_financials_task; print(evaluate_agent_financials_task.name)"`
Expected: `recommendations.evaluate_agent_financials`

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/analysis.py
git commit -m "feat: add async financial evaluation Celery task (Phase 4)"
```

---

### Task 9: Update Schema and API Routes

**Files:**
- Modify: `backend/app/schemas/recommendation.py`
- Modify: `backend/app/api/routes/recommendations.py`

- [ ] **Step 1: Add new fields to RecommendationResponse**

In `backend/app/schemas/recommendation.py`, add to `RecommendationResponse`:

```python
    agent_opportunity_json: dict
    linked_step_ids: list
    domain_id: UUID | None
    financial_evaluation_status: str
```

- [ ] **Step 2: Add `confidence` sort option to API routes**

In `backend/app/api/routes/recommendations.py`, add to the `_SORTABLE` dict:

```python
    "confidence": Recommendation.composite_score,
```

- [ ] **Step 3: Add `financial_evaluation_status` to the status endpoint response**

In the `recommendation_pipeline_status` function, add `financial_evaluation_status` info. After the existing return dict construction, add a count of pending financial evaluations:

```python
    pending_financial = await db.scalar(
        select(func.count()).select_from(Recommendation).where(
            Recommendation.org_id == org.id,
            Recommendation.recommendation_run_id == run.id if run else None,
            Recommendation.financial_evaluation_status == "pending",
        )
    ) if run else 0
```

Then add `"pending_financial_evaluations": int(pending_financial or 0)` to the returned dict.

- [ ] **Step 4: Verify the app starts**

Run: `cd backend && python -c "from app.schemas.recommendation import RecommendationResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/app/api/routes/recommendations.py
git commit -m "feat: update recommendation schema and API routes for agent opportunities"
```

---

### Task 10: Update Chat Context for Agent Opportunities

**Files:**
- Modify: `backend/app/services/chat/context.py`

- [ ] **Step 1: Include agent_opportunity_json in recommendation anchor payload**

In `backend/app/services/chat/context.py`, in the `at == "recommendation"` branch of `_anchor_context` (around line 158), add `agent_opportunity_json` to the `anchor_payload["recommendation"]` dict:

```python
                "agent_opportunity": dict(rec.agent_opportunity_json) if rec.agent_opportunity_json else {},
```

Add it after `"narrative"` and before `"scoring"`. This gives the chat LLM visibility into the agent opportunity details (topics, replaces, trigger, data_requirements) when the user opens a recommendation for enrichment.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/chat/context.py
git commit -m "feat: include agent_opportunity_json in recommendation chat context"
```

---

### Task 11: Clean Up Deprecated Files

**Files:**
- Delete: `backend/app/services/recommendations/heuristic_scorer.py`
- Delete: `backend/app/services/recommendations/candidate_generator.py`
- Delete: `backend/app/services/recommendations/llm_scorer.py`

- [ ] **Step 1: Verify no remaining imports of deprecated modules**

Search the codebase for imports of these modules. The only consumer should have been `pipeline.py`, which was rewritten in Task 7. If any other files import them, update those imports first.

Run: `cd backend && grep -r "from app.services.recommendations.heuristic_scorer\|from app.services.recommendations.candidate_generator\|from app.services.recommendations.llm_scorer" app/`

Expected: No matches (pipeline.py was rewritten and no longer imports these).

- [ ] **Step 2: Delete the files**

```bash
git rm backend/app/services/recommendations/heuristic_scorer.py
git rm backend/app/services/recommendations/candidate_generator.py
git rm backend/app/services/recommendations/llm_scorer.py
```

- [ ] **Step 3: Verify the app still starts**

Run: `cd backend && python -c "from app.services.recommendations.pipeline import run_recommendation_pipeline; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove deprecated heuristic_scorer, candidate_generator, llm_scorer"
```

---

### Task 12: Integration Smoke Test

**Files:**
- Create: `backend/tests/services/recommendations/test_pipeline_integration.py`

- [ ] **Step 1: Write a smoke test that verifies the pipeline imports and orchestration structure**

Create `backend/tests/services/recommendations/test_pipeline_integration.py`:

```python
"""Integration smoke tests for the agent opportunity pipeline."""

import pytest


def test_pipeline_imports():
    """Verify all pipeline modules import without errors."""
    from app.services.recommendations.domain_assembler import assemble_domain_contexts
    from app.services.recommendations.agent_analyzer import analyze_domain
    from app.services.recommendations.cross_domain import synthesize_cross_domain
    from app.services.recommendations.pipeline import run_recommendation_pipeline
    from app.services.recommendations.financial_engine import compute_projections
    from app.workers.analysis import evaluate_agent_financials_task

    assert callable(assemble_domain_contexts)
    assert callable(analyze_domain)
    assert callable(synthesize_cross_domain)
    assert callable(run_recommendation_pipeline)
    assert callable(compute_projections)
    assert evaluate_agent_financials_task.name == "recommendations.evaluate_agent_financials"


def test_domain_assembler_helpers():
    """Verify pure helpers work end-to-end."""
    from app.services.recommendations.domain_assembler import (
        build_actor_roster,
        build_touchpoint_inventory,
        serialize_domain_context,
    )

    procs = [{
        "name": "Test Process",
        "actors": ["Admin", "User"],
        "system_touchpoints": ["Account.Name", "Contact.Email"],
        "steps": [{
            "name": "Step 1",
            "actors": ["User"],
            "system_touchpoints": ["Account.Industry"],
        }],
    }]

    roster = build_actor_roster(procs)
    assert "Admin" in roster
    assert "User" in roster
    assert len(roster["User"]) == 2

    inventory = build_touchpoint_inventory(procs)
    assert "Account" in inventory
    assert "Name" in inventory["Account"]
    assert "Industry" in inventory["Account"]
    assert "Contact" in inventory

    ctx = serialize_domain_context(
        {"id": "x", "name": "Test", "description": None, "narrative": None},
        procs,
        [],
    )
    assert ctx["domain"]["name"] == "Test"
    assert len(ctx["processes"]) == 1
    assert "actor_roster" in ctx


def test_agent_analyzer_parsing():
    """Verify opportunity parsing and validation work end-to-end."""
    from app.services.recommendations.agent_analyzer import (
        parse_opportunity_response,
        validate_opportunity,
        resolve_ids,
    )

    valid_opp = {
        "agent_name": "Test Agent",
        "agent_type": "headless",
        "description": "Does stuff",
        "topics": [{"topic_name": "T", "description": "d", "reasoning_type": "agentic", "actions_needed": []}],
        "replaces": [{"process_id": "abc", "process_name": "P", "steps_replaced": [], "step_ids": [], "replacement_type": "full"}],
        "trigger": "event",
        "data_requirements": [],
        "integration_points": [],
        "complexity_estimate": "medium",
        "confidence": 0.8,
        "rationale": "test",
        "risks": "none",
        "financial_signals": {
            "actors_impacted": [],
            "estimated_hours_per_week_saved": 5,
            "estimated_frequency": "daily",
            "estimated_actor_count": 1,
            "primary_role_type": "operations",
        },
    }

    assert validate_opportunity(valid_opp) is True
    assert validate_opportunity({"agent_name": "", "topics": []}) is False

    result = parse_opportunity_response({"agent_opportunities": [valid_opp]})
    assert len(result["agent_opportunities"]) == 1
```

- [ ] **Step 2: Run all recommendation tests**

Run: `cd backend && python -m pytest tests/services/recommendations/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/services/recommendations/test_pipeline_integration.py
git commit -m "test: add integration smoke tests for agent opportunity pipeline"
```
