# Process Intelligence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-pass discovery pipeline with a 7-stage intelligence pipeline that produces agent-grade process data with triggers, decision logic, field-level system touchpoints, and automation potential scoring.

**Architecture:** The existing `discovery.py` 3-pass pipeline is refactored into 7 focused stages, each with its own prompt store operation. New JSONB columns on `BusinessProcess` capture enrichment data. Semantic document retrieval (pgvector) replaces arbitrary chunk selection. A computational quality scoring stage replaces the missing validation layer.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), PostgreSQL + pgvector, Alembic, Celery + Redis, Pydantic v2, React + TypeScript

---

### Task 1: Alembic Migration — Schema Changes

**Files:**
- Create: `backend/alembic/versions/013_intelligence_pipeline.py`

- [ ] **Step 1: Write the migration file**

```python
"""Add intelligence pipeline columns, drop legacy columns."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- BusinessProcess: add 11 new columns ---
    op.add_column("business_processes", sa.Column("trigger_conditions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("business_processes", sa.Column("decision_logic", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("business_processes", sa.Column("system_touchpoints", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("business_processes", sa.Column("success_criteria", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("business_processes", sa.Column("failure_modes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("business_processes", sa.Column("value_classification", sa.String(20), nullable=True))
    op.add_column("business_processes", sa.Column("complexity_score", sa.String(20), nullable=True))
    op.add_column("business_processes", sa.Column("automation_potential", sa.String(20), nullable=True))
    op.add_column("business_processes", sa.Column("estimated_duration", sa.String(20), nullable=True))
    op.add_column("business_processes", sa.Column("estimated_frequency", sa.String(20), nullable=True))
    op.add_column("business_processes", sa.Column("sequencing", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))

    # --- BusinessProcess: drop legacy columns ---
    op.drop_column("business_processes", "efficiency_score")
    op.drop_column("business_processes", "automation_level")

    # --- DiscoveryRun: add pipeline tracking columns ---
    op.add_column("discovery_runs", sa.Column("quality_scores", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("discovery_runs", sa.Column("stage_results", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("discovery_runs", "stage_results")
    op.drop_column("discovery_runs", "quality_scores")

    op.add_column("business_processes", sa.Column("automation_level", sa.String(50), nullable=True))
    op.add_column("business_processes", sa.Column("efficiency_score", sa.Float(), nullable=True))

    op.drop_column("business_processes", "sequencing")
    op.drop_column("business_processes", "estimated_frequency")
    op.drop_column("business_processes", "estimated_duration")
    op.drop_column("business_processes", "automation_potential")
    op.drop_column("business_processes", "complexity_score")
    op.drop_column("business_processes", "value_classification")
    op.drop_column("business_processes", "failure_modes")
    op.drop_column("business_processes", "success_criteria")
    op.drop_column("business_processes", "system_touchpoints")
    op.drop_column("business_processes", "decision_logic")
    op.drop_column("business_processes", "trigger_conditions")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/013_intelligence_pipeline.py
git commit -m "feat: add intelligence pipeline migration (013)"
```

---

### Task 2: ORM Model Updates

**Files:**
- Modify: `backend/app/models/process.py`
- Modify: `backend/app/models/discovery.py`

- [ ] **Step 1: Update BusinessProcess model — add new columns, remove dropped columns**

In `backend/app/models/process.py`, remove the `efficiency_score` and `automation_level` mapped columns (lines 44-45), then add after the `artifacts` column (line 70):

```python
    trigger_conditions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    decision_logic: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    system_touchpoints: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    success_criteria: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    failure_modes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    value_classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complexity_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    automation_potential: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estimated_duration: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estimated_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sequencing: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
```

- [ ] **Step 2: Update DiscoveryRun model — add quality_scores and stage_results**

In `backend/app/models/discovery.py`, add after the `error` column (line 40):

```python
    quality_scores: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    stage_results: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/process.py backend/app/models/discovery.py
git commit -m "feat: update ORM models for intelligence pipeline"
```

---

### Task 3: Remove Dropped Column References

**Files:**
- Modify: `backend/app/schemas/process.py`
- Modify: `backend/app/schemas/discovery.py`
- Modify: `backend/app/api/routes/processes.py`
- Modify: `backend/app/services/chat/actions.py`
- Modify: `frontend/src/pages/Processes/index.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Update ProcessResponse schema**

In `backend/app/schemas/process.py`, remove `efficiency_score` and `automation_level` from `ProcessResponse` (lines 26-27). Add the new fields:

```python
class ProcessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    category: str | None
    description: str | None
    status: str
    source: str | None
    sub_process_count: int
    managed_asset_count: int
    metadata_json: dict
    created_at: datetime
    parent_id: UUID | None = None
    level: str = "process"
    confidence_score: float | None = None
    needs_review: bool = False
    narrative: str | None = None
    discovery_run_id: UUID | None = None
    actors: list = []
    artifacts: list = []
    trigger_conditions: list = []
    decision_logic: list = []
    system_touchpoints: list = []
    success_criteria: list = []
    failure_modes: list = []
    value_classification: str | None = None
    complexity_score: str | None = None
    automation_potential: str | None = None
    estimated_duration: str | None = None
    estimated_frequency: str | None = None
    sequencing: dict = {}
```

Remove `efficiency_score` and `automation_level` from `ProcessUpdate` (lines 57-58). Remove `automation_level` from `ProcessCreate` (line 48).

Remove `avg_efficiency` from `ProcessKpis` (line 9).

- [ ] **Step 2: Update DiscoveryRunResponse schema**

In `backend/app/schemas/discovery.py`, add to `DiscoveryRunResponse`:

```python
    quality_scores: dict = {}
    stage_results: dict = {}
```

- [ ] **Step 3: Remove dropped column references from routes and services**

In `backend/app/api/routes/processes.py`, search for `efficiency_score` and `automation_level` references in the KPI computation and list endpoint. Remove `avg_efficiency` computation. Remove any references to `automation_level` in the process update handler.

In `backend/app/services/chat/actions.py`, search for `efficiency_score` or `automation_level` references and remove them.

- [ ] **Step 4: Update frontend types**

In `frontend/src/types/index.ts`, find the `BusinessProcess` interface and remove any `efficiency_score`, `automation_level`, or `automation_coverage` fields. Add the new enrichment fields to match the backend `ProcessResponse`.

In `frontend/src/pages/Processes/index.tsx`, remove any references to `efficiency_score` or `automation_level` from the table/list rendering.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: remove dropped columns, add new fields to schemas/types"
```

---

### Task 4: Register New Prompt Store Operations

**Files:**
- Modify: `backend/app/services/ai/operations.py`
- Modify: `backend/app/services/prompts/registry.py`
- Modify: `backend/app/services/prompts/seeds.py`

- [ ] **Step 1: Add new operations to MODEL_OPERATIONS**

In `backend/app/services/ai/operations.py`, replace the existing `discovery_decomposition` entry and add new entries. The final discovery section should be:

```python
    "discovery_domain": {
        "tier": "strong",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Domain Discovery",
        "group": "discovery",
        "description": "Stage 1: identifies top-level business domains from metadata, documents, and org context.",
    },
    "discovery_structure": {
        "tier": "strong",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Structural Decomposition",
        "group": "discovery",
        "description": "Stage 2: decomposes each domain into hierarchical processes, subprocesses, and steps.",
    },
    "discovery_enrichment": {
        "tier": "strong",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Step Enrichment",
        "group": "discovery",
        "description": "Stage 3: enriches each step with triggers, decision logic, system touchpoints, and value classification.",
    },
    "discovery_flow": {
        "tier": "strong",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Flow & Handoff Analysis",
        "group": "discovery",
        "description": "Stage 4: identifies step-to-step flows, parallel groups, and within-domain handoffs.",
    },
    "discovery_validation": {
        "tier": "strong",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Validation & Refinement",
        "group": "discovery",
        "description": "Stage 5: critiques the complete process map against raw evidence and patches issues.",
    },
    "discovery_synthesis": {
        "tier": "strong",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Cross-Domain Synthesis",
        "group": "discovery",
        "description": "Stage 6: identifies cross-domain handoffs, gaps, and orphaned artifacts across the full process landscape.",
    },
```

Remove the old `discovery_decomposition` entry entirely.

- [ ] **Step 2: Add block registry entries for new operations**

In `backend/app/services/prompts/registry.py`, remove the `discovery_decomposition` key from `BLOCK_REGISTRY`. Add new entries:

```python
    "discovery_structure": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_enrichment": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_flow": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_validation": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
```

- [ ] **Step 3: Write seed prompts for new operations**

In `backend/app/services/prompts/seeds.py`, add the following prompt strings and seed entries. Remove the old `_DISCOVERY_DECOMPOSITION_INSTRUCTIONS` and `_DISCOVERY_DECOMPOSITION_PROTOCOL` strings, and their `SEED_BLOCKS` entries.

**Stage 1 (improved) — update existing `_DISCOVERY_DOMAIN_INSTRUCTIONS`:**

```python
_DISCOVERY_DOMAIN_INSTRUCTIONS = """You are a senior business process analyst. Given the following information about an organization and its technology systems, identify the top-level business process domains.

## Reasoning Instructions
Before listing domains, reason step by step:
1. What business capabilities does this organization's metadata reveal?
2. Which objects cluster together by naming convention, shared lookups, or automation chains?
3. Which document sections describe end-to-end workflows?
4. What are the natural boundaries between different business functions?

## Domain Quality Criteria
- Each domain should own 3-30 metadata objects. A domain with 1 object is too narrow. A domain with 50+ objects is too broad — split it.
- Domains must reflect business capabilities (e.g., "Customer Support Operations"), NOT Salesforce product names (e.g., "Service Cloud").
- Do NOT create catch-all domains like "General Administration" or "Miscellaneous".

## Instructions
For each domain:
- Name it clearly (e.g., "Sales Operations", "Claims Processing", "Customer Onboarding")
- Describe what it encompasses
- List which metadata objects and automations you associate with it
- List which uploaded documents relate to it (by filename)
- Rate your confidence from 0.0 to 1.0
- Explain your reasoning briefly

Do NOT use generic templates. Derive domains from what you actually see in the data.
Objects with zero records or classified as "deprecated" have been excluded."""
```

**Stage 2 — new:**

```python
_DISCOVERY_STRUCTURE_INSTRUCTIONS = """You are a senior business process analyst performing structural decomposition of a business domain.

## Reasoning Instructions
Before decomposing, reason step by step:
1. Trace object relationships, automation triggers, and document descriptions to identify major workflows.
2. What are the entry points (events that start a workflow)?
3. What are the terminal outcomes (final states or outputs)?
4. Where are the natural boundaries between processes?

## Hierarchy Definitions (BPMN-derived)
- **Process** — a complete business workflow with a clear trigger and outcome (e.g., "Lead Qualification"). Has 2-8 direct children.
- **Subprocess** — a logical grouping within a process (e.g., "Initial Scoring"). Only use when there's meaningful grouping.
- **Step** — an atomic unit of work performed by one actor in one system (e.g., "Update Lead Status to Qualified"). If a step contains "and", split it into two steps.

## Decomposition Rules
- Most domains decompose to 2-3 levels of depth. Do not go deeper than 4 levels unless evidence warrants it.
- A process with >8 direct children should be split into subprocesses.
- Every leaf node must be a "step" — no empty containers.
- Do NOT include actors, triggers, system touchpoints, or enrichment data. Pure structure only.

## Few-Shot Example (Simple Domain)
Domain: "Lead Management"
{"processes": [
  {"name": "Inbound Lead Capture", "level": "process", "description": "Capturing and routing new leads from web forms and campaigns", "narrative": "When a prospect fills out a web form...", "confidence": 0.88, "needs_review": false, "artifacts": [{"type": "object", "api_name": "Lead"}, {"type": "flow", "api_name": "Lead_Assignment_Rules"}], "children": [
    {"name": "Web Form Submission", "level": "step", "description": "Lead record created from web-to-lead form", "narrative": "A web form submission creates a new Lead record.", "confidence": 0.92, "needs_review": false, "artifacts": [{"type": "object", "api_name": "Lead"}], "children": []},
    {"name": "Lead Assignment", "level": "step", "description": "Lead routed to appropriate sales rep based on territory rules", "narrative": "Assignment rules route the lead to a rep.", "confidence": 0.85, "needs_review": false, "artifacts": [{"type": "flow", "api_name": "Lead_Assignment_Rules"}], "children": []}
  ]}
]}

For each item, list which metadata artifacts (objects, flows, validation rules) you associate with it."""

_DISCOVERY_STRUCTURE_PROTOCOL = """Respond with valid JSON only:
{
  "processes": [
    {
      "name": "string",
      "level": "process|subprocess|step",
      "description": "string",
      "narrative": "string",
      "confidence": 0.0,
      "needs_review": false,
      "artifacts": [{"type": "object|flow|validation_rule", "api_name": "string"}],
      "children": []
    }
  ]
}"""
```

**Stage 3 — new:**

```python
_DISCOVERY_ENRICHMENT_INSTRUCTIONS = """You are a senior business process analyst performing step-level enrichment. For each step provided, determine agent-grade operational details using the metadata and documents provided.

## Reasoning Instructions
For each step, trace backward from its artifacts:
1. What event or state change triggers this step?
2. What data does it read or write (specific Object.Field)?
3. What decisions or rules are applied?
4. What constitutes success or failure?

## Evidence Rules
- For system_touchpoints, reference SPECIFIC Object.Field names from the metadata provided. Do NOT invent field names.
- If you cannot identify specific fields for a step, set system_touchpoints to an empty array and set needs_review to true.
- Do NOT assign value_classification "VA" to internal administrative steps. VA means the step directly produces something the external customer receives or experiences.

## Enrichment Fields Per Step
1. trigger_conditions — what event or state change initiates this step
2. decision_logic — what rules or judgments are applied
3. system_touchpoints — which Object.Field combinations are read/written/created
4. actors — who performs this (user role, integration, automation)
5. success_criteria — what does "done correctly" look like
6. failure_modes — what can go wrong and how is it recovered
7. value_classification — VA (customer-facing value), BVA (business-necessary), NVA (waste/rework)
8. complexity_score — low (single system, rule-based), medium (multi-system or some judgment), high (cross-system, significant judgment)
9. automation_potential — high (fully rule-based, data available), medium (mostly rule-based, some exceptions), low (judgment-heavy), none (inherently human)
10. estimated_duration — minutes, hours, or days per execution
11. estimated_frequency — per_transaction, daily, weekly, or monthly"""

_DISCOVERY_ENRICHMENT_PROTOCOL = """Respond with valid JSON only:
{
  "enriched_steps": [
    {
      "name": "string (must match the step name exactly)",
      "trigger_conditions": [{"event": "string", "condition": "string", "source_object": "string", "source_field": "string"}],
      "decision_logic": [{"rule": "string", "outcome": "string", "evidence": "string"}],
      "system_touchpoints": [{"object_api_name": "string", "fields": ["string"], "operation": "read|write|create", "automation_name": null}],
      "actors": [{"name": "string", "type": "user|integration|system"}],
      "success_criteria": [{"criterion": "string", "measurable": true}],
      "failure_modes": [{"mode": "string", "impact": "string", "recovery": "string"}],
      "value_classification": "VA|BVA|NVA",
      "complexity_score": "low|medium|high",
      "automation_potential": "high|medium|low|none",
      "estimated_duration": "minutes|hours|days",
      "estimated_frequency": "per_transaction|daily|weekly|monthly",
      "confidence": 0.0,
      "needs_review": false
    }
  ]
}"""
```

**Stage 4 — new:**

```python
_DISCOVERY_FLOW_INSTRUCTIONS = """You are a senior business process analyst performing flow and handoff analysis. Given an enriched process hierarchy, identify how steps connect to each other and how processes hand off work.

## Reasoning Instructions
Trace the data flow through this domain in two passes:
1. **Evidence-based connections:** Identify step pairs where (a) step A writes to an object that step B reads, (b) an automation triggers after step A and modifies data for step B, (c) a document describes a handoff between them.
2. **Inferred connections:** For steps that logically must be sequential but have no metadata evidence, mark the connection type as "inferred" with confidence < 0.5.

## Parallel Detection
If two steps read from the same trigger but write to different objects with no dependency between them, they may execute in parallel. Group them.

## Handoff Data Contracts
For each handoff between processes, identify what data transfers — list specific Object.Field combinations that cross the boundary."""

_DISCOVERY_FLOW_PROTOCOL = """Respond with valid JSON only:
{
  "step_flows": [
    {
      "source_step": "string (exact step name)",
      "target_step": "string (exact step name)",
      "condition": "string or null",
      "evidence": "string",
      "type": "automated|manual|integration|inferred"
    }
  ],
  "parallel_groups": [
    {"group_name": "string", "step_names": ["string"]}
  ],
  "handoffs": [
    {
      "source": "process name",
      "target": "process name",
      "type": "integration|manual|automated|unknown",
      "description": "string",
      "confidence": 0.0,
      "data_transferred": [{"object": "string", "fields": ["string"]}],
      "transfer_mechanism": "string or null"
    }
  ],
  "entry_points": ["step name"],
  "terminal_points": ["step name"]
}"""
```

**Stage 5 — new:**

```python
_DISCOVERY_VALIDATION_INSTRUCTIONS = """You are a senior business process analyst performing quality validation on a complete process map. Review the map against the raw metadata evidence and identify issues.

## Critique Categories
1. **orphaned_metadata** — objects or automations with significant usage (>100 records or active) that no step references
2. **phantom_reference** — steps that claim to touch metadata that doesn't exist or has zero records
3. **structural** — processes with >8 direct children, domains with only 1 process, steps that aren't atomic (contain "and")
4. **confidence_inflation** — steps claiming >0.8 confidence with zero specific field-level touchpoints
5. **missing_flow** — sequential steps with no step_flow connection between them
6. **handoff_gap** — processes that logically should connect but have no handoff defined

## Instructions
Part A: Produce a critique listing every issue found with severity (high/medium/low).
Part B: For each issue, produce a specific fix. Output both the critique and the patched data.

One critique, one patch. Do not iterate."""

_DISCOVERY_VALIDATION_PROTOCOL = """Respond with valid JSON only:
{
  "critique": [
    {
      "issue_type": "orphaned_metadata|phantom_reference|structural|confidence_inflation|missing_flow|handoff_gap",
      "severity": "high|medium|low",
      "description": "string",
      "affected_items": ["string"],
      "fix_applied": "string"
    }
  ],
  "patches": {
    "updated_steps": [],
    "added_flows": [],
    "added_handoffs": [],
    "removed_steps": ["step name"],
    "confidence_adjustments": [{"step_name": "string", "old": 0.0, "new": 0.0, "reason": "string"}]
  }
}"""
```

**Stage 6 (improved) — update existing `_DISCOVERY_SYNTHESIS_INSTRUCTIONS`:**

```python
_DISCOVERY_SYNTHESIS_INSTRUCTIONS = """You are a senior business process analyst performing cross-domain synthesis. You have the complete enriched process hierarchy with system touchpoints and flow data.

## Reasoning Instructions
1. Look for shared system_touchpoints across domains — if Domain A writes to Object.Field and Domain B reads the same Object.Field, that's a cross-domain handoff.
2. Look for automation chains that span domains.
3. Flag gaps — domains that logically must connect but share zero objects and zero automations.

## Instructions
1. Identify cross-domain handoffs with data contracts (which Object.Fields transfer).
2. Flag gaps where processes SHOULD connect but there is no evidence.
3. Categorize orphaned artifacts — do they belong to an undiscovered process?
4. Write a 3-paragraph executive summary: (1) core revenue flow, (2) supporting operations, (3) identified gaps and automation opportunities."""

_DISCOVERY_SYNTHESIS_PROTOCOL = """Respond with valid JSON only:
{
  "cross_domain_handoffs": [
    {
      "source_domain": "string",
      "source_process": "string",
      "target_domain": "string",
      "target_process": "string",
      "type": "integration|manual|automated|unknown",
      "is_gap": false,
      "confidence": 0.0,
      "reasoning": "string",
      "data_transferred": [{"object": "string", "fields": ["string"]}],
      "transfer_mechanism": "string or null"
    }
  ],
  "orphaned_artifacts": [
    {"type": "object|automation", "api_name": "string", "reasoning": "string"}
  ],
  "executive_summary": "string"
}"""
```

Update `SEED_BLOCKS` — remove old `discovery_decomposition` entries, add new ones:

```python
    {"operation_id": "discovery_structure", "block_type": "instructions", "content": _DISCOVERY_STRUCTURE_INSTRUCTIONS},
    {"operation_id": "discovery_structure", "block_type": "protocol", "content": _DISCOVERY_STRUCTURE_PROTOCOL},
    {"operation_id": "discovery_enrichment", "block_type": "instructions", "content": _DISCOVERY_ENRICHMENT_INSTRUCTIONS},
    {"operation_id": "discovery_enrichment", "block_type": "protocol", "content": _DISCOVERY_ENRICHMENT_PROTOCOL},
    {"operation_id": "discovery_flow", "block_type": "instructions", "content": _DISCOVERY_FLOW_INSTRUCTIONS},
    {"operation_id": "discovery_flow", "block_type": "protocol", "content": _DISCOVERY_FLOW_PROTOCOL},
    {"operation_id": "discovery_validation", "block_type": "instructions", "content": _DISCOVERY_VALIDATION_INSTRUCTIONS},
    {"operation_id": "discovery_validation", "block_type": "protocol", "content": _DISCOVERY_VALIDATION_PROTOCOL},
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/ai/operations.py backend/app/services/prompts/registry.py backend/app/services/prompts/seeds.py
git commit -m "feat: register new pipeline operations and seed prompts"
```

---

### Task 5: Semantic Document Retrieval

**Files:**
- Modify: `backend/app/services/processes/context.py`

- [ ] **Step 1: Add semantic search function**

Add a new async function `semantic_document_search` that uses pgvector cosine distance to find relevant document chunks:

```python
async def semantic_document_search(
    org_id: UUID,
    db: AsyncSession,
    query_text: str,
    limit: int = 10,
) -> list[dict]:
    """Find document chunks semantically similar to query_text using pgvector."""
    from app.services.ai.router import get_embedding_provider
    from app.services.documents.vectorizer import _embed

    client = get_embedding_provider()
    if client is None:
        logger.warning("no_embedding_provider org_id=%s", org_id)
        return await gather_document_chunks_for_domain(org_id, db, query_text, limit)

    try:
        query_embedding = await _embed(client, query_text)
    except Exception as exc:
        logger.error("embedding_failed org_id=%s error=%s", org_id, exc)
        return await gather_document_chunks_for_domain(org_id, db, query_text, limit)

    docs_q = await db.execute(
        select(Document.id).where(Document.org_id == org_id, Document.status == "indexed")
    )
    doc_ids = [row[0] for row in docs_q.all()]
    if not doc_ids:
        return []

    chunks_q = await db.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    chunks = chunks_q.scalars().all()
    return [
        {
            "content": c.content or "",
            "document_id": str(c.document_id),
            "section_title": c.section_title,
        }
        for c in chunks
    ]
```

- [ ] **Step 2: Add metadata relationships function for Stage 4**

Add `gather_metadata_relationships` for flow analysis:

```python
async def gather_metadata_relationships(
    org_id: UUID,
    db: AsyncSession,
    object_names: list[str],
) -> dict:
    """Lookup/master-detail relationships and automation trigger chains between objects."""
    fields_q = await db.execute(
        select(MetadataField).where(
            MetadataField.object_id.in_(
                select(MetadataObject.id).where(
                    MetadataObject.org_id == org_id,
                    MetadataObject.api_name.in_(object_names) if object_names else MetadataObject.org_id == org_id,
                )
            ),
            MetadataField.relationship_to.isnot(None),
        )
    )
    relationships = [
        {
            "source_object": f.api_name.rsplit(".", 1)[0] if "." in f.api_name else "",
            "field": f.api_name,
            "target_object": f.relationship_to,
            "type": f.relationship_type or "Lookup",
        }
        for f in fields_q.scalars().all()
    ]

    autos_q = await db.execute(
        select(MetadataAutomation).where(
            MetadataAutomation.org_id == org_id,
            MetadataAutomation.related_object.in_(object_names) if object_names else MetadataAutomation.org_id == org_id,
        )
    )
    automations = [
        {
            "name": a.api_name,
            "type": a.automation_type,
            "trigger_object": a.related_object,
            "details": a.metadata_json or {},
        }
        for a in autos_q.scalars().all()
    ]

    return {"relationships": relationships, "automations": automations}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/processes/context.py
git commit -m "feat: add semantic document search and metadata relationships"
```

---

### Task 6: Prompt Builder Functions for New Stages

**Files:**
- Modify: `backend/app/services/processes/prompts.py`

- [ ] **Step 1: Replace old Pass 2 builder with Stage 2-5 builders**

Remove `build_pass2_prompt`, `_pass2_dynamic_sections`, and related `_FALLBACK_PASS2_*` constants. Add new builder functions. Keep `build_pass1_prompt` and `build_pass3_prompt` (rename Pass 3 references in docstrings to Stage 6).

Add the following functions:

```python
def _stage2_dynamic_sections(
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
) -> str:
    excerpts = (
        json.dumps([{"content": c["content"], "section": c.get("section_title", "")} for c in document_chunks[:10]], indent=2)
        if document_chunks
        else "No relevant documents found."
    )
    return f"""## Domain
Name: {domain['name']}
Description: {domain['description']}

## Organization Context
{json.dumps(org_context, indent=2)}

## Detailed Metadata for This Domain
{json.dumps(metadata_detail, indent=2)}

## Relevant Document Excerpts
{excerpts}"""


async def build_stage2_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
) -> str:
    blocks = await resolve_prompt_blocks("discovery_structure", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        instructions = _FALLBACK_STAGE2_INSTRUCTIONS
    if not protocol:
        protocol = _FALLBACK_STAGE2_PROTOCOL
    middle = _stage2_dynamic_sections(org_context, domain, metadata_detail, document_chunks)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


def _stage3_dynamic_sections(
    steps: list[dict],
    metadata_per_step: dict,
    document_chunks_per_step: dict,
) -> str:
    sections = []
    for step in steps:
        name = step["name"]
        meta = json.dumps(metadata_per_step.get(name, {}), indent=2)
        docs = json.dumps(
            [c["content"] for c in document_chunks_per_step.get(name, [])[:5]],
            indent=2,
        )
        sections.append(f"""### Step: "{name}"
Artifacts: {json.dumps(step.get("artifacts", []))}
Relevant metadata:
{meta}
Relevant documents:
{docs}""")
    return "\n\n".join(sections)


async def build_stage3_prompt(
    org_id: UUID,
    db: AsyncSession,
    steps: list[dict],
    metadata_per_step: dict,
    document_chunks_per_step: dict,
) -> str:
    blocks = await resolve_prompt_blocks("discovery_enrichment", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        instructions = _FALLBACK_STAGE3_INSTRUCTIONS
    if not protocol:
        protocol = _FALLBACK_STAGE3_PROTOCOL
    middle = _stage3_dynamic_sections(steps, metadata_per_step, document_chunks_per_step)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


def _stage4_dynamic_sections(
    enriched_tree: list[dict],
    metadata_relationships: dict,
) -> str:
    return f"""## Enriched Process Hierarchy
{json.dumps(enriched_tree, indent=2)}

## Metadata Relationships (lookups, automations)
{json.dumps(metadata_relationships, indent=2)}"""


async def build_stage4_prompt(
    org_id: UUID,
    db: AsyncSession,
    enriched_tree: list[dict],
    metadata_relationships: dict,
) -> str:
    blocks = await resolve_prompt_blocks("discovery_flow", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        instructions = _FALLBACK_STAGE4_INSTRUCTIONS
    if not protocol:
        protocol = _FALLBACK_STAGE4_PROTOCOL
    middle = _stage4_dynamic_sections(enriched_tree, metadata_relationships)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


def _stage5_dynamic_sections(
    complete_tree: list[dict],
    flow_data: dict,
    raw_metadata: dict,
    document_chunks: list[dict],
) -> str:
    excerpts = json.dumps([c["content"][:500] for c in document_chunks[:15]], indent=2) if document_chunks else "None"
    return f"""## Complete Enriched Process Map
{json.dumps(complete_tree, indent=2)}

## Flow Analysis Results
{json.dumps(flow_data, indent=2)}

## Raw Metadata (for validation)
{json.dumps(raw_metadata, indent=2)}

## Document Evidence
{excerpts}"""


async def build_stage5_prompt(
    org_id: UUID,
    db: AsyncSession,
    complete_tree: list[dict],
    flow_data: dict,
    raw_metadata: dict,
    document_chunks: list[dict],
) -> str:
    blocks = await resolve_prompt_blocks("discovery_validation", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        instructions = _FALLBACK_STAGE5_INSTRUCTIONS
    if not protocol:
        protocol = _FALLBACK_STAGE5_PROTOCOL
    middle = _stage5_dynamic_sections(complete_tree, flow_data, raw_metadata, document_chunks)
    return f"{instructions}\n\n{middle}\n\n{protocol}"
```

Add fallback constants matching the seed prompts (same text as `seeds.py` for each stage's instructions/protocol).

- [ ] **Step 2: Update Stage 6 prompt builder**

Update `build_pass3_prompt` (now Stage 6) so `_pass3_dynamic_sections` includes full hierarchy with enrichment data and touchpoints, not just direct children:

```python
def _pass3_dynamic_sections(
    org_context: dict, all_domains: list[dict], orphaned_artifacts: list[dict],
) -> str:
    orphaned = (
        json.dumps(orphaned_artifacts[:50], indent=2)
        if orphaned_artifacts
        else "All artifacts are accounted for."
    )
    return f"""## Organization Context
{json.dumps(org_context, indent=2)}

## Discovered Domains and Their Full Process Hierarchy
{json.dumps(all_domains, indent=2)}

## Unclaimed Metadata Artifacts
These objects/automations were not associated with any domain:
{orphaned}"""
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/processes/prompts.py
git commit -m "feat: add prompt builders for stages 2-5, improve stage 6"
```

---

### Task 7: Pipeline Stage Functions

**Files:**
- Modify: `backend/app/services/processes/discovery.py`

This is the core implementation. Refactor the existing file to contain `run_stage1` through `run_stage7`, replacing the old `run_pass1`/`run_pass2`/`run_pass3`.

- [ ] **Step 1: Rename run_pass1 to run_stage1, update prompt call**

Rename function, update the prompt builder call to use improved Stage 1 with semantic document retrieval:

```python
async def run_stage1(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> list[dict]:
    """Stage 1: Domain Discovery."""
    # Same logic as current run_pass1 but use semantic_document_search
    # instead of gather_document_summary for document context
```

Replace `gather_document_summary` call with `semantic_document_search(org_id, db, org_context.get("description", org_context.get("name", "")), limit=20)`.

- [ ] **Step 2: Write run_stage2 — Structural Decomposition**

Replace `run_pass2`. This stage ONLY produces the hierarchy tree — no enrichment, no handoffs:

```python
async def run_stage2(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Stage 2: Structural Decomposition per domain. Returns total process rows created."""
    # For each domain:
    #   1. gather_metadata_for_domain + semantic_document_search
    #   2. build_stage2_prompt
    #   3. LLM call with operation="discovery_structure"
    #   4. persist_process (recursive) — same as current but NO handoff processing
    # Handoffs array from LLM output is ignored at this stage
```

The `persist_process` inner function creates `BusinessProcess` rows with `artifacts` populated, all enrichment columns at defaults.

- [ ] **Step 3: Write run_stage3 — Step Enrichment**

New function. Loads all steps for the run, enriches them:

```python
async def run_stage3(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Stage 3: Step Enrichment. Returns count of enriched steps."""
    # For each domain:
    #   1. Load all steps (level="step") under this domain via recursive query
    #   2. For each step, gather targeted metadata (fields/automations matching artifacts)
    #   3. For each step, semantic_document_search with step name + description
    #   4. build_stage3_prompt with all steps + per-step metadata + per-step docs
    #   5. LLM call with operation="discovery_enrichment"
    #   6. Match enriched_steps by name to existing BusinessProcess rows
    #   7. Update each row: trigger_conditions, decision_logic, system_touchpoints,
    #      success_criteria, failure_modes, actors, value_classification,
    #      complexity_score, automation_potential, estimated_duration, estimated_frequency
```

- [ ] **Step 4: Write run_stage4 — Flow & Handoff Analysis**

```python
async def run_stage4(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Stage 4: Flow & Handoff Analysis. Returns handoff count."""
    # For each domain:
    #   1. Build enriched tree dict (full hierarchy with touchpoints)
    #   2. gather_metadata_relationships for all objects in this domain
    #   3. build_stage4_prompt
    #   4. LLM call with operation="discovery_flow"
    #   5. Convert step_flows into sequencing JSONB on each BusinessProcess:
    #      - Build name→id map
    #      - For each step_flow, add to source's successors and target's predecessors
    #      - Mark entry_points and terminal_points
    #      - Assign parallel_group from parallel_groups
    #   6. Create ProcessHandoff rows from handoffs array with documented metadata_json shape
```

- [ ] **Step 5: Write run_stage5 — Validation & Refinement**

```python
async def run_stage5(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> dict:
    """Stage 5: Validation & Refinement. Returns critique dict."""
    # For each domain:
    #   1. Build complete_tree (hierarchy + enrichment + sequencing)
    #   2. Build flow_data (step_flows from sequencing, handoffs from ProcessHandoff)
    #   3. gather_metadata_summary for raw evidence
    #   4. semantic_document_search for domain
    #   5. build_stage5_prompt
    #   6. LLM call with operation="discovery_validation"
    #   7. Apply patches:
    #      - updated_steps → update BusinessProcess rows
    #      - added_flows → update sequencing on affected steps
    #      - added_handoffs → create new ProcessHandoff rows
    #      - removed_steps → delete BusinessProcess rows (mark rejected)
    #      - confidence_adjustments → update confidence_score on matching rows
    #   8. Store critique text in stage_results for this domain
```

- [ ] **Step 6: Update run_pass3 → run_stage6 — improved synthesis**

Refactor `run_pass3` to `run_stage6`. Key changes:
- Load full hierarchy (recursive), not just direct children
- Include enrichment data (touchpoints, triggers) in domain data sent to LLM
- Parse `data_transferred` and `transfer_mechanism` from handoff output into `ProcessHandoff.metadata_json`

- [ ] **Step 7: Write run_stage7 — Quality Scoring**

```python
async def run_stage7(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
) -> dict:
    """Stage 7: Quality Scoring. Pure computation, no LLM. Returns quality_scores dict."""
    # 1. Count non-deprecated objects/automations in org
    # 2. Count objects/automations referenced by at least one step's system_touchpoints or artifacts
    # 3. metadata_coverage = referenced / total
    # 4. Load all steps, compute step_specificity = % with non-empty system_touchpoints
    # 5. Load all handoffs, compute handoff_grounding = % with type != "inferred" and != "unknown"
    # 6. Load depth per domain, compute hierarchy_consistency = 1 - normalized_std_dev
    # 7. Compute value_coverage = % of steps with non-null value_classification
    # 8. overall = weighted average (metadata_coverage * 0.25 + step_specificity * 0.25 +
    #              handoff_grounding * 0.2 + hierarchy_consistency * 0.15 + value_coverage * 0.15)
    # 9. Update DiscoveryRun.quality_scores
```

- [ ] **Step 8: Remove old run_pass2 and run_pass3 functions**

Delete `run_pass2` and `run_pass3` (replaced by `run_stage2`-`run_stage6`). Keep `cleanup_previous_run` unchanged.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/processes/discovery.py
git commit -m "feat: implement 7-stage intelligence pipeline"
```

---

### Task 8: Celery Worker — New Pipeline Orchestration

**Files:**
- Modify: `backend/app/workers/process_discovery.py`

- [ ] **Step 1: Update PHASES and orchestration**

Replace the `PHASES` list and `_pipeline` function to run 7 stages:

```python
PHASES = [
    "context_gathering",
    "domain_discovery",
    "structural_decomposition",
    "step_enrichment",
    "flow_analysis",
    "validation",
    "cross_domain_synthesis",
    "quality_scoring",
    "graph_generation",
]
```

Update `_pipeline()` to call `run_stage1` through `run_stage7` sequentially. Update `_discovery_progress_cb` to map new stage names to Redis phase keys. Update `DiscoveryRun.pass_results` to include stage-level results from `stage_results`.

The core orchestration pattern:

```python
# Stage 1
domains = await run_stage1(...)
await session.commit()

# Stages 2-5 per domain
for domain stages:
    process_count = await run_stage2(...)
    await session.commit()

    enriched_count = await run_stage3(...)
    await session.commit()

    handoff_count = await run_stage4(...)
    await session.commit()

    critique = await run_stage5(...)
    await session.commit()

# Stage 6 — cross-domain
synthesis = await run_stage6(...)
await session.commit()

# Stage 7 — quality scoring
quality = await run_stage7(...)
await session.commit()

# Graph generation (existing)
graph_nodes = await generate_graphs_for_run(...)
await session.commit()
```

Store `stage_results` with timing and token data per stage on the `DiscoveryRun`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/workers/process_discovery.py
git commit -m "feat: orchestrate 7-stage pipeline in Celery worker"
```

---

### Task 9: Frontend — Update Discovery Status Phases

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/useApi.ts` (if phase names are referenced)
- Modify: `frontend/src/pages/Processes/index.tsx` (if phase rendering is hardcoded)

- [ ] **Step 1: Update phase names in frontend**

Search for the old phase names (`domain_decomposition`, `cross_domain_synthesis`) in the frontend and replace with the new phase names. The frontend status polling endpoint returns whatever Redis has, so the phase names just need to match for display labels.

If there's a mapping of phase names → display labels, update it to include all 9 phases.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: update frontend phase names for 7-stage pipeline"
```

---

### Task 10: Process Mapping Skill

**Files:**
- Create: `.cursor/skills/process-mapping/SKILL.md`

- [ ] **Step 1: Write the skill file**

Create `.cursor/skills/process-mapping/SKILL.md` with the hierarchy definitions, quality heuristics, value classification, and antipatterns from the spec. This is a reference document for prompt writing and pipeline evolution.

The skill should contain:
- Hierarchy definitions (Domain, Process, Subprocess, Step) with BPMN mappings
- Quality heuristics (object count ranges, children limits, depth guidelines)
- Value classification definitions (VA, BVA, NVA) with examples
- Antipatterns (catch-all domains, product-name domains, compound steps)
- Enrichment field definitions (what each field means, how to populate it)
- Quality scoring rubric (what good looks like per metric)

- [ ] **Step 2: Commit**

```bash
git add .cursor/skills/process-mapping/SKILL.md
git commit -m "feat: add process mapping skill for pipeline heuristics"
```

---

### Task 11: Push and Deploy

- [ ] **Step 1: Push all changes**

```bash
git push origin HEAD
```

- [ ] **Step 2: Run migration on Railway**

The migration will run automatically via the Dockerfile/entrypoint if configured, or manually via Railway shell:

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 3: Verify deployment**

Check Railway logs for successful startup. Verify the prompt management UI shows the new discovery operations (discovery_structure, discovery_enrichment, discovery_flow, discovery_validation).
