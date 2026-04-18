# Process Intelligence Pipeline

**Date:** 2026-04-18
**Status:** Draft
**Supersedes:** Sections of `2026-04-17-process-discovery-engine-design.md` (LLM Pipeline Architecture, Data Model changes for enrichment columns)

## Problem

The current 3-pass discovery pipeline produces map-grade process data: names, descriptions, hierarchy, basic actors/artifacts. This is sufficient for visualization but insufficient for the downstream recommendation engine to design agent blueprints.

To build agents from discovered processes, each step needs **trigger conditions, decision logic, field-level system touchpoints, success/failure criteria, value classification, and automation potential**. The current pipeline cannot produce this because:

1. Pass 2 asks a single monolithic prompt to decompose structure AND enrich details AND identify handoffs — too many concerns dilute quality
2. No validation pass — errors and hallucinations propagate unchecked
3. Document retrieval is arbitrary (chunk offset) not semantic
4. No BPMN hierarchy guidance — the LLM invents inconsistent depth structures
5. No quality scoring — no way to measure or optimize output quality
6. Handoffs use name-matching (collision-prone) with no data contract

## Design Principles

All principles from the original spec remain. Additional:

- **Single responsibility per stage.** Each pipeline stage does one thing well. Structure, enrichment, flow analysis, and validation are separate concerns with separate prompts.
- **Evidence grounding.** Every claim references specific metadata or document evidence. No unsupported assertions.
- **Rational marginal returns.** Every pipeline step must justify its cost in measurable quality improvement.
- **Prompt library is source of truth.** All prompts live in the prompt store (`PromptBlock`), not in code. Code contains bootstrap fallbacks only.

## Process Mapping Skill

A `.cursor/skills/process-mapping/SKILL.md` codifies the research into reusable heuristics. Referenced by prompts and pipeline code.

### Hierarchy Definitions (BPMN-derived)

- **Domain** — top-level business capability area (e.g., "Sales Operations", "Claims Processing"). Owns 3-30 metadata objects. Maps to a BPMN Pool.
- **Process** — complete business workflow with a clear trigger and outcome (e.g., "Lead Qualification"). Maps to a BPMN Process. Has 2-8 direct children.
- **Subprocess** — logical grouping within a process (e.g., "Initial Scoring"). Maps to a BPMN Sub-Process. Optional level — only used when there's meaningful grouping.
- **Step** — atomic unit of work performed by one actor in one system (e.g., "Update Lead Status to Qualified"). Maps to a BPMN Task. If it contains "and", split it.

### Quality Heuristics

- A domain with 1 object is too narrow. A domain with 50+ objects is too broad.
- A process with >8 direct children should be split into subprocesses.
- A step claiming >0.8 confidence with zero field-level touchpoints is likely inflated.
- Every handoff must cite a metadata artifact or document. No phantom handoffs.
- Depth should be 2-3 levels for most domains. >4 levels requires strong evidence.

### Value Classification (Lean)

- **VA (Value-Added):** Directly serves the external customer. The customer would pay for this.
- **BVA (Business Value-Added):** Necessary for the business to operate but not customer-facing. Regulatory, compliance, internal reporting.
- **NVA (Non-Value-Added):** Waste, rework, unnecessary handoffs, manual data entry that could be automated.

### Antipatterns

- Catch-all domains ("General Administration", "Miscellaneous")
- Domains that mirror product names ("Service Cloud") instead of business capabilities ("Customer Support Operations")
- Steps that describe multiple actions ("Review and Approve" — split into "Review" and "Approve")
- Handoffs asserted without evidence
- Processes with zero steps (empty containers)

## 7-Stage Pipeline Architecture

```
Stage 1: Domain Discovery          (discovery_domain — improved)
    |
Stage 2: Structural Decomposition  (discovery_structure — new)
    |
Stage 3: Step Enrichment           (discovery_enrichment — new)
    |
Stage 4: Flow & Handoff Analysis   (discovery_flow — new)
    |
Stage 5: Validation & Refinement   (discovery_validation — new)
    |
Stage 6: Cross-Domain Synthesis    (discovery_synthesis — improved)
    |
Stage 7: Quality Scoring           (no LLM call — pure computation)
```

Stages 2-5 run per domain. Stage 6 runs across all domains. Stage 7 runs once.

### Stage 1: Domain Discovery — `discovery_domain`

**Input:** Org context + metadata summary + top-20 semantic document chunks (by embedding similarity to org description).

**Prompt improvements:**
- Chain-of-Thought preamble: "Before listing domains, reason about what business capabilities the metadata and documents reveal. Which objects cluster together?"
- Domain quality criteria: "Each domain should own 3-30 metadata objects."
- Antipattern injection: "Do NOT create domains that mirror Salesforce product names."
- Semantic document retrieval replaces arbitrary document summary.

**Output schema:** Unchanged from current.

**Persistence:** Domain `BusinessProcess` rows with `level = "domain"`, `parent_id = null`.

### Stage 2: Structural Decomposition — `discovery_structure`

**Input:** One domain definition + full metadata for associated objects (field-level, validation rules, flow metadata) + top-10 semantic document chunks for the domain.

**Prompt strategy:**
- CoT: "Trace object relationships, automation triggers, and document descriptions to identify major workflows."
- BPMN definitions embedded from skill.
- 2 few-shot examples (simple and complex domain).
- Step atomicity rule: "If a step contains 'and', split it."
- Depth guidance: "2-3 levels for most domains. Do not exceed 4 without strong evidence."
- **Pure structure only.** No actors, triggers, touchpoints, or enrichment fields requested.

**Output schema:**
```json
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
}
```

**Persistence:** `BusinessProcess` rows with hierarchy. `artifacts` column populated. All enrichment columns left as defaults.

### Stage 3: Step Enrichment — `discovery_enrichment`

**Input:** Stage 2 tree (flattened to steps) + targeted metadata per step (fields, automations matching each step's artifacts) + top-5 semantic document chunks per step.

**Prompt strategy:** Structured enrichment template per step. For each step, determine:
1. Trigger conditions
2. Decision logic
3. System touchpoints (Object.Field level)
4. Actors
5. Success criteria
6. Failure modes
7. Value classification (VA/BVA/NVA)
8. Complexity score (low/medium/high)
9. Automation potential (high/medium/low/none)
10. Estimated duration (minutes/hours/days)
11. Estimated frequency (per_transaction/daily/weekly/monthly)

Evidence rule: "Reference specific Object.Field names from provided metadata. Do NOT invent field names. If unable, set touchpoints empty and flag needs_review."

**Output schema:**
```json
{
  "enriched_steps": [
    {
      "name": "string (must match Stage 2 step name)",
      "trigger_conditions": [{"event": "string", "condition": "string", "source_object": "string", "source_field": "string"}],
      "decision_logic": [{"rule": "string", "outcome": "string", "evidence": "string"}],
      "system_touchpoints": [{"object_api_name": "string", "fields": ["string"], "operation": "read|write|create", "automation_name": "string|null"}],
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
}
```

**Persistence:** Updates existing `BusinessProcess` step rows with enrichment columns. `system_touchpoints` is the agent-grade source of truth post-enrichment.

### Stage 4: Flow & Handoff Analysis — `discovery_flow`

**Input:** Enriched tree (full hierarchy with touchpoints) + metadata relationships (lookups, master-detail, automation trigger-to-target chains).

**Prompt strategy:**
- Two-pass reasoning: (1) evidence-based connections (shared objects, automation chains, document references), (2) inferred connections (logical flow, marked with confidence < 0.5).
- Handoff data contracts: "For each handoff, list specific Object.Field combinations that cross the boundary."
- Parallel detection: "Steps reading from same trigger but writing to different objects with no dependency may execute in parallel."

**Output schema:**
```json
{
  "step_flows": [
    {
      "source_step": "string",
      "target_step": "string",
      "condition": "string|null",
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
      "transfer_mechanism": "string|null"
    }
  ],
  "entry_points": ["step name"],
  "terminal_points": ["step name"]
}
```

**Persistence:**
- `step_flows` + `parallel_groups` + `entry_points` + `terminal_points` converted into the `sequencing` JSONB on each `BusinessProcess` step row.
- `handoffs` become `ProcessHandoff` rows with documented `metadata_json` shape (see Data Model section).

### Stage 5: Validation & Refinement — `discovery_validation`

**Input:** Complete enriched tree + flow analysis + original raw metadata + document chunks.

**Prompt strategy (Refine-n-Judge):**

Part A — Critique. Identify:
1. Orphaned metadata — objects/automations with significant usage that no step references
2. Phantom references — steps claiming metadata that doesn't exist or has zero records
3. Structural issues — processes with >8 children, domains with 1 process, non-atomic steps
4. Confidence inflation — high confidence with zero field-level touchpoints
5. Missing flows — sequential steps with no connection
6. Handoff gaps — processes that logically should connect but have no handoff

Part B — Patch. For each issue, produce a specific fix.

One critique, one patch. No iterative loops.

**Output schema:**
```json
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
}
```

**Persistence:** Patches applied to existing rows. Critique text stored in `DiscoveryRun.stage_results.stage_5.critique`.

### Stage 6: Cross-Domain Synthesis — `discovery_synthesis`

**Improvements over current Pass 3:**
- Sees full hierarchy (all levels) with enrichment data (touchpoints, flows)
- Cross-domain handoff detection via shared `system_touchpoints` across domains
- Evidence-based gap detection: "Two domains share zero objects and zero automations but logically must connect."
- Data contracts enforced on cross-domain handoffs
- Improved executive summary prompt: core revenue flow, supporting operations, identified gaps and automation opportunities

**Output schema:** Same structure as current, plus `data_transferred` and `transfer_mechanism` on each handoff.

### Stage 7: Quality Scoring — no LLM call

Pure computation on the pipeline output:

| Metric | Formula |
|--------|---------|
| `metadata_coverage` | % of non-deprecated objects/automations referenced by at least one step |
| `hierarchy_consistency` | 1 - normalized std dev of depth across domains |
| `step_specificity` | % of steps with >= 1 Object.Field in system_touchpoints |
| `handoff_grounding` | % of handoffs with metadata evidence (vs inferred) |
| `value_coverage` | % of steps with VA/BVA/NVA assigned |
| `overall` | Weighted composite of the above |

Stored on `DiscoveryRun.quality_scores`.

## Data Model Changes

### BusinessProcess — New Columns

| Column | Type | Default | Populated By |
|--------|------|---------|-------------|
| `trigger_conditions` | JSONB | `[]` | Stage 3 |
| `decision_logic` | JSONB | `[]` | Stage 3 |
| `system_touchpoints` | JSONB | `[]` | Stage 3 (source of truth post-enrichment) |
| `success_criteria` | JSONB | `[]` | Stage 3 |
| `failure_modes` | JSONB | `[]` | Stage 3 |
| `value_classification` | String(20) | null | Stage 3 |
| `complexity_score` | String(20) | null | Stage 3 |
| `automation_potential` | String(20) | null | Stage 3 |
| `estimated_duration` | String(20) | null | Stage 3 |
| `estimated_frequency` | String(20) | null | Stage 3 |
| `sequencing` | JSONB | `{}` | Stage 4 |

### BusinessProcess — Dropped Columns

| Column | Reason |
|--------|--------|
| `efficiency_score` | Replaced by `value_classification` + `estimated_duration` + `estimated_frequency` |
| `automation_level` | Replaced by `automation_potential` + `complexity_score` + `system_touchpoints` |

### BusinessProcess — Unchanged Enrichment Columns

- `actors` — populated by Stage 3, simple actor list
- `artifacts` — frozen after Stage 2, represents discovery-time metadata associations (not source of truth post-enrichment; `system_touchpoints` is)

### DiscoveryRun — New Columns

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `quality_scores` | JSONB | `{}` | Stage 7 metrics |
| `stage_results` | JSONB | `{}` | Per-stage `{ duration_ms, tokens_in, tokens_out }` + Stage 5 `critique` text |

### ProcessHandoff — No Schema Change

Documented `metadata_json` shape enforced by Stage 4/6 prompts:
```json
{
  "data_transferred": [{"object": "string", "fields": ["string"]}],
  "transfer_mechanism": "string|null",
  "source_process": "string",
  "target_process": "string",
  "source_domain": "string",
  "target_domain": "string"
}
```

### Sequencing JSONB Shape

```json
{
  "predecessors": [{"step_id": "uuid", "condition": null}],
  "successors": [{"step_id": "uuid", "condition": "amount > 50k"}],
  "parallel_group": "approval|null",
  "is_entry_point": false,
  "is_terminal": false
}
```

## Prompt Store Operations

### Existing (improved)

| Operation ID | Stage | Changes |
|-------------|-------|---------|
| `discovery_domain` | 1 | CoT preamble, domain quality criteria, antipatterns, semantic doc retrieval |
| `discovery_decomposition` | 2 | Replaced by `discovery_structure`. Old seeds and PromptBlock rows deleted by migration seed. |
| `discovery_synthesis` | 6 | Full hierarchy input, shared-touchpoint detection, data contracts |

### New

| Operation ID | Tier | Group |
|-------------|------|-------|
| `discovery_structure` | strong | discovery |
| `discovery_enrichment` | strong | discovery |
| `discovery_flow` | strong | discovery |
| `discovery_validation` | strong | discovery |

Each gets `instructions` + `protocol` blocks. Protocol blocks are non-editable per existing pattern.

## Context Gathering Improvements

### Semantic Document Retrieval

Stages 1, 2, and 3 use vector search against `DocumentChunk` embeddings:
- Stage 1: top-20 chunks by similarity to org description
- Stage 2: top-10 chunks by similarity to domain name + description
- Stage 3: top-5 chunks per step by similarity to step name + description

Replaces current arbitrary chunk selection (offset-based).

### Expanded Metadata for Stages 2-4

`gather_metadata_for_domain` enhanced to include:
- Field-level detail (names, types, descriptions, formulas)
- Validation rule formulas
- Flow trigger configs (entry conditions, DML types)

New `gather_metadata_relationships` for Stage 4:
- Lookup/master-detail field relationships between objects
- Automation trigger→target chains (Flow triggers on Object A, creates/updates Object B)

## Orchestration

- Same Celery worker pattern
- Stages run sequentially within a domain (2→3→4→5), then Stage 6 across all domains, then Stage 7
- Redis progress phases: `context_gathering`, `domain_discovery`, `structural_decomposition`, `step_enrichment`, `flow_analysis`, `validation`, `cross_domain_synthesis`, `quality_scoring`, `graph_generation`
- Graceful degradation: if a stage fails for one domain after retry, mark domain `needs_review` and continue with remaining domains
- Langfuse tracing per stage

## DSPy Integration (Phase 2 — deferred)

Not built in Phase 1. Phase 1 prepares the infrastructure:
- Quality scoring (Stage 7) provides objective functions
- Prompt store org-level overrides provide the write-back mechanism
- Confirm/reject signals on processes provide human feedback
- Structured prompt separation (instructions vs protocol) already exists

DSPy optimization service bolts on as a background worker that tests prompt variants against Stage 7 metrics and writes winners to the prompt store.

## Migration Strategy

Single Alembic migration:
- Add 11 JSONB/String columns to `business_processes` (all nullable or JSON-defaulted)
- Drop 2 columns from `business_processes` (`efficiency_score`, `automation_level`)
- Add 2 JSONB columns to `discovery_runs`
- Remove all backend/frontend references to dropped columns

## What This Spec Does NOT Include

- DSPy implementation (Phase 2)
- Multi-agent decomposition (Phase 3)
- Incremental discovery / process diff (Phase 3)
- Cross-org learning (Phase 3)
- Frontend enrichment data visualization (separate ticket — display trigger_conditions, touchpoints, etc. in process detail views)
- Metadata enrichment improvements (Layer 1 — separate spec)
