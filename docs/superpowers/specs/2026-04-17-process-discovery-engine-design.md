# Process Discovery Engine

**Date:** 2026-04-17
**Status:** Draft

## Problem

Arcflare ingests platform metadata and business documents but cannot yet synthesize them into a coherent picture of how the business operates. The existing process generation (`mine_from_metadata`, `mine_from_documents`) is stubbed. The current `BusinessProcess` model is flat — no hierarchy, no handoffs, no confidence scoring, no gap detection.

The goal is to auto-discover business processes from system metadata + uploaded documents + organization intelligence, produce a structured, hierarchical process graph with narrative summaries, and flag areas where the system lacks confidence or detects gaps between processes.

## Vision Context

This is Layer 3 of a six-layer platform architecture:

1. **Metadata Enrichment** — richer Salesforce metadata (deferred; this spec defines what it needs)
2. **Document Ingestion** — upload workflow guides, training docs, SOPs (partially built)
3. **Process Discovery Engine** — this spec
4. **Gap Analysis** — find disconnected processes, missing integrations (future)
5. **ABOS Recommendations** — where agentic workflows add the most value (future)
6. **Visualization** — interactive process flow diagrams (partially built via ReactFlow)

## Design Principles

- **No pre-baked process templates.** The system discovers processes from data, not by matching against industry-specific templates. A Health Cloud org and a manufacturing org will produce completely different process hierarchies.
- **Organization context grounds everything.** The LLM knows the business model, industry, ICP, and revenue structure (from web-scraped org intelligence) before it looks at metadata. This dramatically reduces hallucination.
- **Autonomous with escalation.** High-confidence discoveries go straight to the map. Low-confidence areas are flagged as "needs human input" rather than guessed at.
- **Hierarchical and recursive.** Processes nest arbitrarily deep. The LLM determines depth based on what it finds — not a fixed template.

## Data Model Changes

### Updated `BusinessProcess`

The existing model evolves to support hierarchy, confidence, and richer semantics:

| Column | Type | Change | Purpose |
|---|---|---|---|
| `parent_id` | UUID FK (self) | **New** | Nullable. Points to parent process. Top-level domains have null. |
| `level` | String(50) | **New** | `domain`, `process`, `subprocess`, `step`. LLM-assigned. |
| `confidence_score` | Float | **New** | 0.0–1.0. How confident the system is in this discovery. |
| `needs_review` | Boolean | **New** | Flagged when confidence is below threshold or data is ambiguous. |
| `narrative` | Text | **New** | LLM-generated natural language summary of this process. |
| `discovery_run_id` | UUID | **New** | Groups all processes from a single discovery run for versioning. |
| `actors` | JSONB | **New** | List of actors involved: `[{ "name": "Sales Rep", "type": "user" }, { "name": "DocuSign", "type": "integration" }]` |
| `artifacts` | JSONB | **New** | Linked metadata: `[{ "type": "object", "api_name": "Opportunity", "id": "..." }, { "type": "flow", "api_name": "Opp_Approval", "id": "..." }]` |
| `status` | String(50) | **Modified** | Values: `discovered`, `confirmed`, `rejected`, `published`. Replaces `draft`/`published`. |

Existing columns `efficiency_score`, `automation_level`, `source`, `sub_process_count`, `managed_asset_count` are retained but may be computed differently.

### New `ProcessHandoff`

First-class entity representing connections between processes (especially cross-domain):

```
ProcessHandoff
  id: UUID PK
  org_id: UUID FK → organizations
  source_process_id: UUID FK → business_processes
  target_process_id: UUID FK → business_processes
  handoff_type: String(50)  -- "integration", "manual", "automated", "unknown"
  description: Text
  confidence_score: Float
  is_gap: Boolean  -- true if this handoff is inferred but not evidenced
  needs_review: Boolean
  discovery_run_id: UUID
  metadata_json: JSONB
```

Gap analysis (Layer 4) queries `ProcessHandoff WHERE is_gap = true`.

### New `DiscoveryRun`

Tracks each execution of the pipeline:

```
DiscoveryRun
  id: UUID PK
  org_id: UUID FK → organizations
  status: String(50)  -- "running", "completed", "failed"
  started_at: DateTime
  completed_at: DateTime
  pass_results: JSONB  -- per-pass metadata (token usage, timings, counts)
  config: JSONB  -- snapshot of settings used for this run
  created_by: String  -- "system" or user identifier
```

### ProcessNode / ProcessEdge

These existing tables continue to serve the ReactFlow visualization. They are **derived** from the process hierarchy + handoffs, not the source of truth. A rebuild step generates nodes/edges from the process graph for rendering.

## LLM Pipeline Architecture

Three sequential passes. Each pass produces structured JSON that is validated, persisted, and fed into the next pass.

### Pass 1 — Domain Discovery

**Trigger:** User clicks "Generate" on the Processes page.

**Input:**
- Organization intelligence (industry, business model, ICP, revenue structure from `Organization.settings_json` and web-scraped enrichment)
- High-level metadata summary: object names + labels + record counts + classification, automation names + types, component categories + counts. **Not** field-level detail.
- Document corpus summary: document titles, section headings, key terms (extracted from `DocumentChunk` via RAG summary query).

**Prompt strategy:** Single prompt. Ask the LLM to identify the top-level business process domains present in this organization. For each domain: name, description, confidence score, which metadata artifacts and document sections it associates with that domain.

**Output schema:**
```json
{
  "domains": [
    {
      "name": "Sales Operations",
      "description": "...",
      "confidence": 0.92,
      "associated_objects": ["Opportunity", "Quote", "PricebookEntry"],
      "associated_automations": ["Opportunity_Approval", "Quote_Generation"],
      "associated_documents": ["sales-playbook.pdf"],
      "reasoning": "High record counts in Opportunity/Quote, active flows..."
    }
  ]
}
```

**Persistence:** Each domain becomes a `BusinessProcess` with `level = "domain"`, `parent_id = null`.

**User checkpoint:** Non-blocking. Pass 2 auto-runs immediately on all discovered domains. The user can retroactively reject or rename domains from the Processes page, which marks child processes as rejected and excludes them from synthesis. A "Re-run Synthesis" action reprocesses Pass 3 with the updated domain set. This respects the "autonomous with escalation" principle — don't make the user wait to approve obvious domains.

### Pass 2 — Process Decomposition (per domain)

**Trigger:** Automatic after Pass 1 (or user clicks "Drill In" on a domain).

**Input (per domain):**
- The domain definition from Pass 1
- Full metadata for objects/automations/components associated with this domain (including field-level detail, validation rules, flow metadata, record types)
- RAG retrieval: document chunks semantically similar to the domain name + description
- Organization context (same as Pass 1)

**Prompt strategy:** One prompt per domain. Ask the LLM to decompose this domain into processes, subprocesses, and steps. For each: name, description, level, actors, artifacts, confidence, narrative. Also identify within-domain handoffs and sequencing.

**Output schema:**
```json
{
  "processes": [
    {
      "name": "Lead Qualification",
      "level": "process",
      "description": "...",
      "narrative": "When a new lead enters the system...",
      "confidence": 0.85,
      "needs_review": false,
      "actors": [{ "name": "SDR", "type": "user" }, { "name": "Pardot", "type": "integration" }],
      "artifacts": [{ "type": "object", "api_name": "Lead" }, { "type": "flow", "api_name": "Lead_Assignment" }],
      "children": [
        {
          "name": "Initial Scoring",
          "level": "subprocess",
          "description": "...",
          "confidence": 0.78,
          "artifacts": [{ "type": "validation_rule", "api_name": "Lead_Score_Required" }],
          "children": []
        }
      ]
    }
  ],
  "handoffs": [
    {
      "source": "Lead Qualification",
      "target": "Opportunity Creation",
      "type": "automated",
      "description": "Lead conversion triggers opportunity creation",
      "confidence": 0.90
    }
  ]
}
```

**Persistence:** Processes, subprocesses, and steps become `BusinessProcess` rows with appropriate `parent_id` and `level`. Handoffs become `ProcessHandoff` rows.

### Pass 3 — Cross-Domain Synthesis

**Trigger:** Automatic after all Pass 2 runs complete.

**Input:**
- The full process graph from all Pass 2 outputs
- Organization context
- Any metadata artifacts that were NOT claimed by any domain in Pass 1 (orphaned objects/automations — these may indicate undiscovered processes or integrations)

**Prompt strategy:** Single prompt. Ask the LLM to:
1. Identify cross-domain handoffs (where does Sales hand to Fulfillment? Where does Support escalate to Engineering?)
2. Flag gaps — processes that should connect but don't have evidence of a connection
3. Identify orphaned metadata that doesn't belong to any discovered process
4. Produce an end-to-end narrative summary of the business

**Output schema:**
```json
{
  "cross_domain_handoffs": [
    {
      "source_domain": "Sales Operations",
      "source_process": "Order Submission",
      "target_domain": "Fulfillment",
      "target_process": "Order Processing",
      "type": "unknown",
      "is_gap": true,
      "confidence": 0.45,
      "reasoning": "No integration or automation connects these processes..."
    }
  ],
  "orphaned_artifacts": [
    { "type": "object", "api_name": "Legacy_Import__c", "reasoning": "..." }
  ],
  "executive_summary": "This organization operates primarily as..."
}
```

**Persistence:** Cross-domain handoffs become `ProcessHandoff` rows. Orphaned artifacts stored in `DiscoveryRun.pass_results`. Executive summary stored on the `DiscoveryRun`.

## Metadata Requirements (Layer 1 Backlog)

The pipeline needs richer metadata than currently captured. These are prioritized by impact on process discovery:

### Critical (blocks meaningful discovery)
- **Flow internals**: Entry conditions, record trigger config (object, DML type), decision branches, DML operations (record creates/updates/deletes), subflow references. Source: Tooling API `Flow` definition body or Metadata API.
- **Validation rule formulas**: `ErrorConditionFormula` from Tooling API. The formula encodes the business rule.
- **Object-level description**: From `describe()` response. Currently not captured.
- **Field-level description**: The actual admin `description`, not just `inlineHelpText` (which we currently map to "description").

### High Value (significantly improves quality)
- **Field formulas**: `calculatedFormula`, `defaultValue` from describe. Encode business logic.
- **Workflow rule criteria and actions**: Entry conditions, field updates, email alerts, outbound messages.
- **Approval process criteria and steps**: Entry criteria, approver matrix, step definitions.

### Nice to Have (improves edge cases)
- **Apex trigger/class bodies**: Source code for imperative logic. Large payloads — may require summarization.
- **Page layout field composition**: Which fields appear on which layouts. Indicates business-relevant fields.
- **FlexiPage type**: Already queried but not persisted in metadata_json.

## Worker Architecture

The discovery pipeline runs as a Celery task (`process_discovery_task`), similar to the existing `sync_metadata_task`. Progress is tracked via Redis using the same `sync_progress` pattern.

**Phases:**
1. `context_gathering` — Load org intelligence + metadata summaries + document summaries
2. `domain_discovery` — Pass 1 LLM call
3. `domain_decomposition` — Pass 2 LLM calls (one per domain, can note progress as "3 of 7 domains")
4. `cross_domain_synthesis` — Pass 3 LLM call
5. `graph_generation` — Rebuild ProcessNode/ProcessEdge from the process hierarchy for ReactFlow rendering

**Langfuse tracing:** Each pass gets its own Langfuse generation event with prompt, response, token usage, and latency. The overall run gets a trace with `discovery_run_id` in metadata.

## Re-run Semantics and Data Integrity

### Full Pipeline Re-run

When the user clicks "Generate" again (or "Re-run" if a previous run exists):

1. A new `DiscoveryRun` is created. The old run's data is **not deleted** until the new run completes successfully.
2. On successful completion, the old run's processes, handoffs, and graph nodes/edges are replaced atomically (delete old → insert new within a single transaction keyed on `discovery_run_id`).
3. If the new run fails, the old data remains untouched. The `DiscoveryRun` is marked `failed` with error details.

This ensures no orphaned or duplicate data — there's always exactly one "current" set of processes per org.

### Per-Pass Re-run

Users can re-run individual passes:

- **Re-run Pass 1 (Domain Discovery):** Replaces all domain-level processes. Cascades: child processes from Pass 2 are deleted, Pass 3 handoffs are deleted. Effectively a full re-run but the user might want this after updating org intelligence.
- **Re-run Pass 2 (for a specific domain):** Replaces all child processes under that domain. Cross-domain handoffs involving that domain's processes are deleted. Pass 3 results are invalidated (marked stale, user prompted to re-run synthesis).
- **Re-run Pass 3 (Synthesis):** Replaces cross-domain handoffs and executive summary only. Domain and process data from Pass 1/2 are untouched.

Each re-run creates a new `DiscoveryRun` (or updates the existing one's `pass_results` for partial re-runs — TBD during implementation based on what's cleaner).

### Staleness Indicators

When a downstream pass is invalidated by an upstream re-run:
- Affected processes get a `stale` flag in their `metadata_json`.
- The UI shows a subtle "outdated" indicator on stale items with a prompt to re-run the relevant pass.

## Pipeline Progress UX

### Stage Progression on Processes Page

The Processes page shows a **persistent pipeline status bar** at the top when a discovery run is active or has completed. Three stages displayed horizontally:

```
[ 1. Domain Discovery ] → [ 2. Process Decomposition ] → [ 3. Cross-Domain Synthesis ]
```

Each stage shows one of four states:
- **Waiting** — gray dot, muted text. Not yet started.
- **Running** — spinning indicator, highlighted border. Shows sub-progress where available (e.g., "Decomposing 3 of 7 domains").
- **Complete** — green check, count summary (e.g., "5 domains found", "23 processes mapped", "4 handoffs, 2 gaps").
- **Failed** — red indicator with error message and "Retry" button.

This bar is **not a modal** — it's inline at the top of the Processes page, always visible while a run is active. After completion it collapses to a summary line ("Last discovery: 5 domains, 23 processes, 2 gaps — 3 min ago") with an expand toggle to see the full stage breakdown.

### Progress Tracking (Backend)

Reuses the Redis `sync_progress` pattern with discovery-specific phases:

```
Phases: context_gathering, domain_discovery, domain_decomposition, cross_domain_synthesis, graph_generation
```

Within `domain_decomposition`, the progress callback reports sub-progress: `"3 of 7 domains"` via the existing `count` + new `total` field on phase info.

The frontend polls `GET /processes/discovery-status` every 2 seconds (same pattern as `useSyncProgress`), which reads from Redis.

### Re-run Controls

After a discovery run completes, each stage in the progression bar shows a subtle "re-run" icon button:
- Stage 1 re-run: warns "This will replace all discovered processes. Continue?"
- Stage 2 re-run: appears per-domain in the domain accordion row, not on the stage bar
- Stage 3 re-run: "Re-run Synthesis" button, no destructive warning needed

The main "Generate" button changes label based on state:
- No prior run: **"Discover Processes"**
- Prior run exists: **"Re-discover"** (with a subtitle: "Replaces current process map")
- Run in progress: **"Discovering…"** (disabled, spinning)

## Frontend Changes

### Processes Page
- Pipeline status bar (described above) replaces the old Generate button area when a run exists
- After completion, the page shows discovered domains as top-level accordion rows
- Each domain row shows: name, description, confidence badge, "needs review" indicator, process count, "Re-run decomposition" action
- Expand a domain to see its child processes, each with their own confidence and review status
- **Confirm/Reject** buttons on `discovered` items to let users validate
- Stale indicators on items invalidated by upstream re-runs

### Process Map Page
- Already functional with ReactFlow. Graph generation step produces nodes/edges from the new hierarchy.
- Future: color-code nodes by confidence, highlight gaps, show handoffs as dashed edges.

### Organization Page — Analysis Settings
- No new settings needed for this spec. LLM model selection uses existing `llm_provider` config.

## What This Does NOT Include

- Interactive process editing (drag-and-drop to restructure hierarchy) — future
- Diff between discovery runs ("what changed since last analysis") — future
- Layer 4 gap analysis UI (dedicated gap report) — future, but data model supports it now
- Layer 5 ABOS recommendations — future
- Metadata enrichment implementation (Layer 1) — separate spec, requirements defined above
- Real-time streaming of LLM output during discovery — future nicety
