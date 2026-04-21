# Recommendation Pipeline — Agentic Automation Value Engine

**Date:** 2026-04-20
**Status:** Draft
**Depends on:** [Discovery Pipeline v2](2026-04-20-discovery-pipeline-v2-design.md) (consumes its output)

## Problem

The discovery pipeline produces rich, evidence-grounded process trees with automation potential scores, value classifications, complexity ratings, system touchpoints, failure modes, and cross-process handoffs. But there is no engine that turns that intelligence into actionable business recommendations — no scoring model, no financial projections, no way for a decision-maker to look at the output and say "yes, automate that, here's the ROI."

The current recommendation system is a single heuristic rule ("if custom objects > 0, suggest rationalization") with a hard-coded composite score. The `Recommendation` model has rich JSONB fields (`impact_json`, `actions_json`, `linked_process_ids`) that are almost entirely unpopulated.

## Goal

Build a recommendation pipeline that:

1. Identifies the most automatable processes as agentic workflow candidates — both individual processes ("discovered") and composite opportunities spanning multiple processes ("synthesized")
2. Scores them with a transparent, auditable formula augmented by LLM reasoning
3. Projects financial value over 5 years with Monte Carlo scenarios (optimistic / expected / conservative)
4. Enables conversational refinement of assumptions via the existing chat framework
5. Presents a portfolio view where decision-makers can select recommendations and see aggregate value curves update in real-time
6. Stubs the handoff to a future AgentScript generator pipeline

## Architecture: Split Brain — Pipeline + Financial Engine

The recommendation system has two distinct execution paths:

**Celery Pipeline** — runs once per trigger (manual). Handles candidate generation, heuristic scoring, LLM scoring/synthesis, and initial financial projection. Produces fully-formed `Recommendation` rows.

**Financial Engine** — a pure, stateless math module. Takes a recommendation's assumptions and returns Monte Carlo projections. Called by the pipeline at the end of a run AND called directly by the API when chat enrichment updates assumptions. No LLM, no tokens burned — instant recalc.

```
┌─────────────────────────────────────────────────────┐
│                  Celery Pipeline                     │
│                                                      │
│  Stage 1: Candidate Generation                       │
│     └─ discovered (from BusinessProcess rows)        │
│     └─ synthesized (LLM cross-process analysis)      │
│                  ↓                                   │
│  Stage 2: Heuristic Scoring                          │
│     └─ deterministic weighted formula                │
│                  ↓                                   │
│  Stage 3: LLM Scoring + Narrative                    │
│     └─ score adjustment (+/- 0.15)                   │
│     └─ narrative justification                       │
│     └─ auto-estimated financial assumptions          │
│                  ↓                                   │
│  Stage 4: Persist + Financial Engine                 │
│     └─ save Recommendation rows                      │
│     └─ run financial engine → scenarios_json         │
└─────────────────────────────────────────────────────┘
              ↓                         ↑
     Recommendation rows         Financial Engine
              ↓                   (pure math, no LLM)
     ┌────────────────┐                ↑
     │  Chat Enrichment │──── update ──┘
     │  (assumptions)   │    assumption
     └────────────────┘
              ↓
     Portfolio View (frontend)
```

---

## Data Model Changes

### New table: `RecommendationRun`

Tracks pipeline execution metadata. Mirrors `DiscoveryRun`.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `UUID` PK | |
| `org_id` | `UUID` FK → organizations | |
| `status` | `String(50)` | pending / running / completed / failed |
| `config` | `JSONB` | discovery_run_id consumed, scoring weights, LLM model |
| `stage_results` | `JSONB` | per-stage timing, candidate counts, token usage |
| `error` | `Text` nullable | failure details |
| `started_at` | `DateTime(tz)` | |
| `completed_at` | `DateTime(tz)` nullable | |

### New columns on `Recommendation`

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `recommendation_type` | `String(20)` | `'discovered'` | `discovered` or `synthesized` |
| `base_score` | `Float` nullable | | heuristic score before LLM adjustment |
| `llm_rationale` | `Text` nullable | | narrative justification from LLM |
| `assumptions_json` | `JSONB` | `{}` | editable financial inputs for the financial engine |
| `scenarios_json` | `JSONB` | `{}` | Monte Carlo output (three scenarios, per-year) |
| `enrichment_log` | `JSONB` | `[]` | append-only log of chat-driven changes (see schema below) |
| `recommendation_run_id` | `UUID` FK → recommendation_runs | nullable | ties to the generating run |

### Existing columns — repurposed

| Column | New usage |
|--------|-----------|
| `composite_score` | Final blended score: `base_score + llm_adjustment` |
| `estimated_roi` | Expected-case 5-year cumulative from `scenarios_json` |
| `impact_json` | Qualitative impact assessment (maintenance, risk, etc.) |
| `analysis_inputs_json` | Raw process enrichment data that fed scoring |
| `actions_json` | Recommended implementation steps |
| `linked_process_ids` | Source process UUIDs (properly populated) |

### `assumptions_json` schema

```json
{
  "fte_annual_cost": 85000,
  "hours_per_week": 4.5,
  "frequency": "daily",
  "actor_count": 3,
  "role_type": "sales_operations",
  "implementation_cost": 15000,
  "adoption_ramp": [0.2, 0.6, 0.9, 0.95, 1.0],
  "efficiency_gain": 0.72,
  "source": "auto_estimated",
  "overrides": {}
}
```

When chat enrichment updates a value, it goes into `overrides` and the original auto-estimate is preserved. The financial engine always uses `override ?? original` for each field.

### `enrichment_log` schema

```json
[
  {
    "timestamp": "2026-04-20T14:30:00Z",
    "source": "chat",
    "thread_id": "uuid",
    "changes": {
      "fte_annual_cost": { "from": 85000, "to": 120000 },
      "actor_count": { "from": 3, "to": 5 }
    },
    "roi_impact": {
      "estimated_roi_before": 182000,
      "estimated_roi_after": 428000
    }
  }
]
```

Each entry captures what changed, who/what changed it, and the impact on the headline ROI number.

### `scenarios_json` schema

```json
{
  "optimistic": {
    "annual_savings": [12000, 38000, 61000, 65000, 68000],
    "cumulative": [12000, 50000, 111000, 176000, 244000],
    "headcount_deflection": [0.1, 0.4, 0.7, 0.8, 0.8],
    "assumptions_multiplier": 1.3
  },
  "expected": {
    "annual_savings": [8000, 28000, 46000, 49000, 51000],
    "cumulative": [8000, 36000, 82000, 131000, 182000],
    "headcount_deflection": [0.08, 0.3, 0.55, 0.6, 0.6],
    "assumptions_multiplier": 1.0
  },
  "conservative": {
    "annual_savings": [4000, 18000, 32000, 34000, 35000],
    "cumulative": [4000, 22000, 54000, 88000, 123000],
    "headcount_deflection": [0.05, 0.2, 0.38, 0.4, 0.4],
    "assumptions_multiplier": 0.7
  },
  "implementation_payback_month": 14,
  "computed_at": "2026-04-20T12:00:00Z"
}
```

---

## Stage 1: Candidate Generation

### Discovered Candidates

Query all `BusinessProcess` rows from the latest completed `DiscoveryRun` for the org. Every process at `level='process'` or `level='subprocess'` with populated enrichment data becomes a candidate. Each candidate inherits all enrichment fields directly.

Filter out processes where `automation_potential = 'low'` AND `value_classification = 'VA'` — these are low-potential, already-valuable processes. Everything else is a candidate. If either field is null, treat it as neutral (include the process as a candidate with reduced evidence strength in heuristic scoring).

### Synthesized Candidates

An LLM pass receives:
- All discovered processes grouped by domain (parent)
- All `ProcessHandoff` records, especially those with `has_gap = True`
- A prompt asking: "Given these processes and their handoffs, identify composite automation opportunities — cases where multiple processes could be collapsed into a single agentic workflow. Focus on: sequential processes with handoff gaps, processes sharing the same system touchpoints, processes with complementary failure modes."

The LLM returns structured JSON with:
- `title`: name for the composite opportunity
- `description`: what the combined agent would do
- `constituent_process_ids`: which processes it spans
- `eliminated_handoffs`: which handoffs it removes
- `rationale`: why combining is better than automating individually

Each synthesized candidate becomes a `Recommendation` with `recommendation_type = 'synthesized'` and `linked_process_ids` set to the constituent processes.

---

## Stage 2: Heuristic Scoring

Deterministic weighted formula over discovery enrichment fields.

### Signal Weights

| Signal | Source | Mapping | Weight |
|--------|--------|---------|--------|
| Automation potential | `automation_potential` | low=0.2, medium=0.5, high=0.9 | 0.25 |
| Value classification | `value_classification` | NVA=0.9, BVA=0.6, VA=0.3 | 0.20 |
| Complexity (inverted) | `complexity_score` | low=0.9, medium=0.6, high=0.3 | 0.15 |
| Evidence strength | `evidence_sources` | count * avg_confidence, normalized 0-1 | 0.15 |
| System touchpoints | `system_touchpoints` | count, capped at 10, normalized 0-1 | 0.10 |
| Failure mode risk | `failure_modes` | count, capped at 8, normalized 0-1 | 0.08 |
| Handoff gap presence | linked `ProcessHandoff.has_gap` | binary: 1 if any gap, 0 otherwise | 0.07 |

**`base_score`** = weighted sum, range 0.0–1.0.

### Scoring Logic

- NVA (Non-Value-Adding) processes score highest — pure waste, best candidates to eliminate
- High automation potential + low complexity = easy win (high score)
- Strong evidence = higher confidence in the recommendation
- More system touchpoints = more integration surface for an agent
- Failure modes and handoff gaps = pain points that automation resolves

### Synthesized Candidate Scoring

For synthesized candidates, the heuristic averages signals across constituent processes and adds a **cross-process bonus** (0.05–0.15) based on the number of handoffs eliminated. Rationale: collapsing 3 processes with 2 handoff gaps into one agent has compounding value beyond the individual process scores.

---

## Stage 3: LLM Scoring + Narrative

Send candidates (batched by domain) to an LLM with their `base_score` and enrichment data.

### LLM responsibilities

1. **Score adjustment** — adjust `base_score` by up to +/- 0.15 with written reasoning. Captures qualitative factors the heuristic can't: organizational context, domain-specific automation patterns, risk considerations.

2. **Narrative generation** — 2-4 sentences explaining why this process is a strong automation candidate, what the agentic workflow would look like, and what business outcome it drives. Written for a non-technical decision-maker.

3. **Auto-estimate financial assumptions** — based on the process enrichment (actors, frequency, duration, role types, system touchpoints), generate reasonable default values for `assumptions_json`. Use industry benchmarks embedded in the prompt:
   - Role-type salary ranges (sales_ops ~$70K, account_executive ~$110K, engineering ~$130K, etc.)
   - Frequency-to-hours mapping (daily + 3 actors + medium complexity ≈ 4-6 hrs/week)
   - Implementation cost estimate based on system touchpoint count and complexity

4. **Recommended actions** — populate `actions_json` with 3-5 concrete implementation steps.

### Output per candidate

```json
{
  "score_adjustment": 0.06,
  "adjustment_rationale": "Strong candidate despite medium complexity — the 4 system touchpoints are all Salesforce-native, reducing integration risk.",
  "narrative": "Lead qualification currently involves 3 AEs manually scoring leads against BANT criteria across Salesforce and HubSpot. An agentic workflow could automate the scoring, route qualified leads to the right AE, and update both systems — eliminating ~4.5 hours/week of manual work per rep.",
  "assumptions": {
    "fte_annual_cost": 110000,
    "hours_per_week": 4.5,
    "frequency": "daily",
    "actor_count": 3,
    "role_type": "account_executive",
    "implementation_cost": 18000,
    "adoption_ramp": [0.2, 0.6, 0.9, 0.95, 1.0],
    "efficiency_gain": 0.72
  },
  "actions": [
    {"step": 1, "action": "Define lead scoring criteria in Agentforce", "effort": "low"},
    {"step": 2, "action": "Build routing logic as Apex action", "effort": "medium"},
    {"step": 3, "action": "Create HubSpot sync agent", "effort": "medium"},
    {"step": 4, "action": "Pilot with one AE team for 2 weeks", "effort": "low"},
    {"step": 5, "action": "Roll out org-wide with monitoring dashboard", "effort": "low"}
  ]
}
```

### Composite score

```
composite_score = base_score + score_adjustment
```

Clamped to [0.0, 1.0]. The `base_score`, `score_adjustment`, and `llm_rationale` are all stored separately so the breakdown is fully auditable.

---

## Stage 4: Persist + Financial Engine

### Persistence

1. Create `RecommendationRun` row with `status = 'running'`
2. Delete previous recommendations for this org that were pipeline-generated (preserve any manually created or user-enriched recommendations with `status = 'accepted'`)
3. Insert all `Recommendation` rows with scores, narratives, assumptions, linked processes
4. Run the financial engine on each recommendation
5. Update `RecommendationRun` to `status = 'completed'` with `stage_results`

### Financial Engine

Pure function. No LLM, no DB access. Signature:

```python
def compute_projections(assumptions: dict, multiplier: float = 1.0) -> dict:
    """Returns annual_savings, cumulative, headcount_deflection for 5 years."""
```

#### Core formula

```
base_savings = fte_annual_cost * (hours_per_week / 40) * actor_count * efficiency_gain
```

Per-year with adoption ramp:

```
year_n_savings = base_savings * adoption_ramp[n] * multiplier
                 - (implementation_cost / multiplier if n == 0 else 0)
```

#### Headcount deflection

```
headcount_deflection[n] = (base_savings * adoption_ramp[n] * multiplier) / fte_annual_cost
```

Not "people fired" — future hires not needed as the org scales.

#### Three scenarios

| Scenario | Multiplier | Meaning |
|----------|-----------|---------|
| Optimistic | 1.3 | Higher efficiency, faster adoption, lower implementation cost |
| Expected | 1.0 | Values as estimated or overridden |
| Conservative | 0.7 | Lower efficiency, slower adoption, higher implementation cost |

The multiplier applies to `efficiency_gain` and `adoption_ramp` values, and inversely to `implementation_cost`.

#### Payback period

```
payback_month = first month where cumulative_savings (expected) > implementation_cost
```

#### Portfolio aggregation

```
portfolio_year_n[scenario] = sum(rec.scenarios[scenario].annual_savings[n] for rec in selected)
```

Each recommendation is independent. No interaction effects in v1.

---

## Chat Enrichment

### Anchor type: `recommendation`

When a chat thread opens with `anchor_type: recommendation`, the system prompt includes:
- The recommendation's title, narrative, scoring breakdown, current assumptions, and current projections
- Linked processes' names, descriptions, and key enrichment fields
- Role instruction: focus on refining financial assumptions, ask targeted questions, call update tools when the user provides information

This is a distinct prompt profile from the discovery chat (which instructs the model NOT to give recommendations).

### Chat tools

**Read-only (auto-execute):**
- `get_recommendation_details` — full recommendation with assumptions and projections
- `get_process_context` — linked process enrichment data
- `get_scoring_breakdown` — heuristic signal weights and values

**Write (proposed action, user confirms):**
- `update_assumption` — updates fields in `assumptions_json.overrides`, triggers financial engine recalc, appends to `enrichment_log`, returns updated projections

### Conversation behavior

The LLM identifies which assumptions are weakest (auto-estimated vs. user-confirmed) and most impactful (which move the ROI needle most), then prioritizes questions accordingly. When the user provides information, the LLM immediately calls `update_assumption` and reports the impact on projections.

### Entry point

Each recommendation card in the frontend gets a "Refine" button that calls `openContextualChat({ type: 'recommendation', id: rec.id })`.

---

## API Changes

### New endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/recommendations/{id}/recalculate` | Update assumption overrides, run financial engine, return updated rec |
| `POST` | `/recommendations/portfolio-projection` | Aggregate projections for selected recs (read-only, does not persist) |
| `GET` | `/recommendations/runs` | List recommendation runs for the org |
| `GET` | `/recommendations/runs/{run_id}` | Run details with stage results |

### Modified endpoints

| Method | Path | Change |
|--------|------|--------|
| `POST` | `/recommendations/generate` | Now creates a `RecommendationRun`, queues the full pipeline |
| `GET` | `/recommendations/{id}` | Response includes new fields (scenarios, assumptions, scoring breakdown) |
| `GET` | `/recommendations/` | Filterable by `recommendation_type`, sortable by `composite_score` or `estimated_roi` |

### Recalculate request/response

```
POST /recommendations/{id}/recalculate
Body: { "overrides": { "fte_annual_cost": 95000, "actor_count": 5 } }

Response: full Recommendation with updated scenarios_json, estimated_roi, enrichment_log
```

### Portfolio projection request/response

```
POST /recommendations/portfolio-projection
Body: { "recommendation_ids": ["uuid1", "uuid2", ...], "global_overrides": {} }

Response: {
  "optimistic": { "annual_savings": [...], "cumulative": [...], "headcount_deflection": [...] },
  "expected": { ... },
  "conservative": { ... },
  "total_payback_month": 11,
  "recommendation_count": 4
}
```

---

## Frontend: Portfolio View & Value Dashboard

### Page structure (3 zones)

**Zone 1: Portfolio Value Dashboard (top)**
- 5-year value curve (Recharts area chart): three lines for optimistic/expected/conservative, confidence band shaded between optimistic and conservative
- Key numbers: total 5-year expected savings, total Year 5 headcount deflection, average payback period, count of selected recommendations
- Updates live as recommendations are toggled in/out from Zone 3

**Zone 2: Recommendation Detail (expandable on click)**
- Scoring breakdown: horizontal bar chart showing each heuristic signal's weighted contribution + LLM adjustment
- Narrative: the LLM-generated justification
- Assumptions table: shows auto-estimated values (tagged), user-overridden values (highlighted), inline editing or "Refine" button for chat
- Individual value curve: same 3-scenario chart for this single recommendation
- Linked processes: clickable links to process tree / domain map
- Actions: "Refine Assumptions" (opens chat), "Accept" (status change), "Dismiss"

**Zone 3: Recommendation List (cards)**
- Each card: title, `recommendation_type` tag (discovered / synthesized), composite score, expected 5-year ROI, category, priority
- Checkbox on each card: toggles inclusion in portfolio dashboard
- Sort/filter by: score, ROI, category, type, status
- Tabs: Active / Accepted / Dismissed

### Agent scaffold stub

Accepted recommendations get a "Generate Agent" button (visible, marked as coming soon). On click:
- Create `Agent` row with `linked_recommendation_id`
- Set `status = 'pending_generation'`
- Populate `config_json` with the recommendation's linked processes, assumptions, and actions
- This is the handoff interface for the future AgentScript generator pipeline

### Real-time updates

When chat updates an assumption via `update_assumption`, the frontend invalidates the TanStack Query cache for that recommendation. The portfolio dashboard re-fetches and Recharts re-renders. No websocket needed — the chat action completes synchronously, the mutation's `onSuccess` triggers cache invalidation.

---

## Out of Scope (future work)

- **AgentScript generation** — the pipeline that consumes accepted recommendations and produces Salesforce AgentScript, Apex actions, and React components. Stubbed with the `Agent` model handoff.
- **Historical comparison** — comparing recommendation runs over time to show progress.
- **Interaction effects** — portfolio-level synergies or conflicts between recommendations (e.g., shared implementation costs).
- **Automated re-scoring** — re-running the LLM stages when discovery is re-run. Currently manual.
- **Org research integration** — feeding `OrgResearchProfile` (industry, company size, growth rate) into the financial assumptions. Natural enrichment source for salary benchmarks and scaling factors.
