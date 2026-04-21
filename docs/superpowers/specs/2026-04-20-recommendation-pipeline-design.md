# Recommendation Pipeline — Agentic Automation Value Engine

**Date:** 2026-04-20
**Status:** Draft
**Depends on:** [Discovery Pipeline v2](2026-04-20-discovery-pipeline-v2-design.md) (consumes its output)

## Problem

The discovery pipeline produces rich, evidence-grounded process trees with automation potential scores, value classifications, complexity ratings, system touchpoints, failure modes, and cross-process handoffs. But there is no engine that turns that intelligence into actionable business recommendations — no scoring model, no financial projections, no way for a decision-maker to look at the output and say "yes, automate that, here's the ROI."

The current recommendation system is a single heuristic rule ("if custom objects > 0, suggest rationalization") with a hard-coded composite score. The `Recommendation` model has rich JSONB fields (`impact_json`, `actions_json`, `linked_process_ids`) that are almost entirely unpopulated.

## Goal

Build a recommendation pipeline that:

1. Identifies the most automatable processes as workflow candidates — both individual processes ("discovered") and composite opportunities spanning multiple processes ("synthesized")
2. Classifies each candidate by automation type (deterministic, agentic, or hybrid) to match the right technology to the right problem
3. Scores them with a transparent, auditable formula augmented by independent LLM reasoning
4. Projects financial value over 5 years with three-scenario sensitivity analysis (optimistic / expected / conservative), splitting hard and soft savings for finance credibility
5. Enables conversational refinement of assumptions via the existing chat framework
6. Presents a portfolio view where decision-makers can select recommendations and see aggregate value curves update in real-time
7. Stubs the handoff to a future AgentScript generator pipeline

## Research Foundation

Design decisions are grounded in these findings:

| Principle | Source | Impact on Design |
|-----------|--------|------------------|
| 62% of failed AI projects used agentic approaches for deterministic tasks | Gartner 2025, multiple 2026 sources | Classify automation type per recommendation |
| CFOs reject soft-only savings; require hard savings tied to cost actions | AFasterExit, DeepSpeed AI 2025 | Split hard vs. soft savings in projections |
| Automation follows a J-Curve; productivity dips before rising | MIT/NANDA, McKinsey Operations 2025-2026 | Model Year 0 productivity dip + inflated implementation cost |
| Additive weighted scores allow "high average, critical flaw" candidates | Algolia engineering, composite scoring research | Multiplicative gate + additive refinement |
| LLMs anchor to provided scores and make small perturbations | CAPO (2026), calibration research | Independent LLM scoring, blend after |
| 3-multiplier scenario analysis is not Monte Carlo | CFA Institute, Advisor Perspectives | Honest naming: "sensitivity analysis" |
| Finance expects NPV at WACC, not raw cumulative savings | Standard corporate finance practice | Add discount rate and NPV |
| Agentic AI has $0.01–$0.50/execution ongoing cost | Applied AI, multiple frameworks | Model ongoing operational cost |

---

## Architecture: Split Brain — Pipeline + Financial Engine

The recommendation system has two distinct execution paths:

**Celery Pipeline** — runs once per trigger (manual). Handles candidate generation, automation type classification, heuristic scoring, LLM scoring/synthesis, and initial financial projection. Produces fully-formed `Recommendation` rows.

**Financial Engine** — a pure, stateless math module. Takes a recommendation's assumptions and returns sensitivity analysis projections. Called by the pipeline at the end of a run AND called directly by the API when chat enrichment updates assumptions. No LLM, no tokens burned — instant recalc.

```
┌─────────────────────────────────────────────────────┐
│                  Celery Pipeline                     │
│                                                      │
│  Stage 1: Candidate Generation + Type Classification │
│     └─ discovered (from BusinessProcess rows)        │
│     └─ synthesized (LLM cross-process analysis)      │
│     └─ classify: deterministic / agentic / hybrid    │
│                  ↓                                   │
│  Stage 2: Heuristic Scoring                          │
│     └─ multiplicative gate + additive refinement     │
│                  ↓                                   │
│  Stage 3: LLM Independent Scoring + Narrative        │
│     └─ independent qualitative score (no anchoring)  │
│     └─ narrative justification                       │
│     └─ auto-estimated financial assumptions          │
│     └─ blend: composite = heuristic*0.7 + llm*0.3   │
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
| `automation_type` | `String(20)` | `'hybrid'` | `deterministic`, `agentic`, or `hybrid` |
| `base_score` | `Float` nullable | | heuristic score (gate * refinement) |
| `llm_score` | `Float` nullable | | independent LLM qualitative score |
| `llm_rationale` | `Text` nullable | | narrative justification from LLM |
| `score_divergence_flag` | `Boolean` | `false` | true when heuristic and LLM scores differ by >0.25 |
| `assumptions_json` | `JSONB` | `{}` | editable financial inputs for the financial engine |
| `scenarios_json` | `JSONB` | `{}` | sensitivity analysis output (three scenarios, per-year) |
| `enrichment_log` | `JSONB` | `[]` | append-only log of chat-driven changes (see schema below) |
| `recommendation_run_id` | `UUID` FK → recommendation_runs | nullable | ties to the generating run |

### Existing columns — repurposed

| Column | New usage |
|--------|-----------|
| `composite_score` | Final blended score: `base_score * 0.7 + llm_score * 0.3` |
| `estimated_roi` | Expected-case 5-year NPV from `scenarios_json` |
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
  "automation_type": "hybrid",
  "technology_cost": 15000,
  "change_management_factor": 0.4,
  "total_investment": 21000,
  "annual_operational_cost": 3600,
  "adoption_ramp": [0.1, 0.5, 0.85, 0.95, 1.0],
  "productivity_dip": 0.05,
  "efficiency_gain": 0.72,
  "discount_rate": 0.10,
  "hard_savings_pct": 0.3,
  "source": "auto_estimated",
  "overrides": {}
}
```

Key changes from research:
- **`technology_cost`** + **`change_management_factor`** (default 0.4) → **`total_investment`** = `technology_cost * (1 + change_management_factor)`. Hidden costs (training, process redesign, organizational learning) account for 40–60% of total investment — the factor captures this.
- **`annual_operational_cost`** — ongoing cost of running the automation. Auto-estimated by `automation_type`: deterministic ~$1,200/yr, agentic = `estimated_executions_per_month * cost_per_execution * 12`, hybrid = blend.
- **`adoption_ramp`** — adjusted to `[0.1, 0.5, 0.85, 0.95, 1.0]`. Research shows pilot-first strategies hit positive ROI at 6–9 months, full-scale at 18–24 months. The old `[0.2, 0.6, ...]` was optimistic.
- **`productivity_dip`** — J-Curve factor. Year 0 net savings are reduced by this fraction of `base_savings` to model the organizational friction during deployment.
- **`discount_rate`** — default 10% (typical enterprise WACC). Used for NPV calculation.
- **`hard_savings_pct`** — fraction of total savings that are hard savings (eliminable cost actions: contractor spend, tool licenses, headcount). Default 0.3 (30%). The rest is soft savings (freed capacity, headcount deflection). Auto-estimated by the LLM, refinable via chat.

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
      "npv_before": 142000,
      "npv_after": 338000
    }
  }
]
```

Each entry captures what changed, who/what changed it, and the impact on the headline NPV number.

### `scenarios_json` schema

```json
{
  "optimistic": {
    "annual_savings": [-5000, 38000, 61000, 65000, 68000],
    "cumulative": [-5000, 33000, 94000, 159000, 227000],
    "hard_savings": [-1500, 11400, 18300, 19500, 20400],
    "soft_savings": [-3500, 26600, 42700, 45500, 47600],
    "headcount_deflection": [0.0, 0.4, 0.7, 0.8, 0.8],
    "assumptions_multiplier": 1.3
  },
  "expected": {
    "annual_savings": [-13000, 24000, 42000, 46000, 48000],
    "cumulative": [-13000, 11000, 53000, 99000, 147000],
    "hard_savings": [-3900, 7200, 12600, 13800, 14400],
    "soft_savings": [-9100, 16800, 29400, 32200, 33600],
    "headcount_deflection": [0.0, 0.28, 0.5, 0.55, 0.56],
    "assumptions_multiplier": 1.0
  },
  "conservative": {
    "annual_savings": [-24000, 12000, 28000, 31000, 33000],
    "cumulative": [-24000, -12000, 16000, 47000, 80000],
    "hard_savings": [-7200, 3600, 8400, 9300, 9900],
    "soft_savings": [-16800, 8400, 19600, 21700, 23100],
    "headcount_deflection": [0.0, 0.14, 0.33, 0.36, 0.39],
    "assumptions_multiplier": 0.7
  },
  "npv": {
    "optimistic": 188000,
    "expected": 112000,
    "conservative": 52000
  },
  "payback_month": {
    "optimistic": 8,
    "expected": 16,
    "conservative": 28
  },
  "computed_at": "2026-04-20T12:00:00Z"
}
```

Key changes from research:
- **Year 0 is negative** — reflects J-Curve productivity dip + total investment. This is honest and what finance expects.
- **`hard_savings` / `soft_savings`** split per year per scenario — CFOs require this distinction. Hard savings count toward ROI forecasts; soft savings are supplementary.
- **`npv`** per scenario — discounted at WACC. This is what finance uses for go/no-go, not raw cumulative.
- **`payback_month`** per scenario — finance prioritizes payback over ROI. Showing it per scenario communicates risk.

---

## Stage 1: Candidate Generation + Type Classification

### Discovered Candidates

Query all `BusinessProcess` rows from the latest completed `DiscoveryRun` for the org. Every process at `level='process'` or `level='subprocess'` with populated enrichment data becomes a candidate. Each candidate inherits all enrichment fields directly.

Filter out processes where `automation_potential = 'low'` AND `value_classification = 'VA'` — these are low-potential, already-valuable processes. Everything else is a candidate. If either field is null, treat it as neutral (include the process as a candidate with reduced evidence strength in heuristic scoring).

### Synthesized Candidates

An LLM pass receives:
- All discovered processes grouped by domain (parent)
- All `ProcessHandoff` records, especially those with `has_gap = True`
- A prompt asking: "Given these processes and their handoffs, identify composite automation opportunities — cases where multiple processes could be collapsed into a single workflow. Focus on: sequential processes with handoff gaps, processes sharing the same system touchpoints, processes with complementary failure modes."

The LLM returns structured JSON with:
- `title`: name for the composite opportunity
- `description`: what the combined workflow would do
- `constituent_process_ids`: which processes it spans
- `eliminated_handoffs`: which handoffs it removes
- `rationale`: why combining is better than automating individually

Each synthesized candidate becomes a `Recommendation` with `recommendation_type = 'synthesized'` and `linked_process_ids` set to the constituent processes.

### Automation Type Classification

Each candidate (discovered and synthesized) is classified into one of three automation types. Classification uses a deterministic decision tree based on process enrichment fields:

| Signal | Deterministic | Agentic | Hybrid |
|--------|--------------|---------|--------|
| `decision_logic` | All entries are rule-based (if/then) | Contains judgment, ambiguity, or "it depends" | Mix of both |
| `trigger_conditions` | Bounded, enumerable triggers | Open-ended, natural language, or contextual | Some bounded, some open |
| `system_touchpoints` | All within one platform (e.g., Salesforce-only) | Cross-platform, unstructured data sources | Mostly one platform with external edges |
| `failure_modes` | Predictable, enumerable failures | Ambiguous failure states, requires interpretation | Core predictable, edge cases ambiguous |
| `actors` | Single role type, consistent behavior | Multiple roles with varying judgment calls | Single role but context-dependent |

**Why this matters for the financial model:**
- **Deterministic:** Near-zero marginal execution cost ($0/execution). Low implementation cost. High reliability. Higher hard savings percentage (eliminates manual work entirely).
- **Agentic:** $0.01–$0.50 per execution (LLM inference). Higher implementation cost (training, guardrails, monitoring). Moderate reliability. Lower hard savings percentage (augments rather than replaces).
- **Hybrid:** Deterministic core handles 70–80% of executions at near-zero cost; agentic handles exceptions. Best economics for most enterprise processes.

The LLM in Stage 3 can override the classification with rationale if the decision tree result seems wrong based on qualitative analysis.

---

## Stage 2: Heuristic Scoring

### Multiplicative Gate + Additive Refinement

Research on composite scoring systems shows that pure additive weighted sums have a critical failure mode: a process can score well overall despite being terrible on a must-have dimension. A process with `automation_potential=low` can still score 0.60+ if everything else is high — producing a recommendation that wastes implementation effort.

The solution: **multiplicative gating** on must-have signals, then **additive refinement** on differentiating signals.

#### Gate signals (multiplicative)

| Signal | Source | Mapping |
|--------|--------|---------|
| Automation potential | `automation_potential` | low=0.15, medium=0.5, high=0.9, null=0.4 |
| Evidence strength | `evidence_sources` | count * avg_confidence, normalized 0-1, minimum 0.1 |

```
gate = automation_potential_score * evidence_strength_score
```

Range: 0.015–0.9. If automation potential is low AND evidence is weak, the gate crushes the total score regardless of other signals. This prevents "high average, critical flaw" recommendations.

#### Refinement signals (additive weighted sum)

| Signal | Source | Mapping | Weight |
|--------|--------|---------|--------|
| Value classification | `value_classification` | NVA=0.9, BVA=0.6, VA=0.3, null=0.5 | 0.30 |
| Complexity (inverted) | `complexity_score` | low=0.9, medium=0.6, high=0.3, null=0.5 | 0.25 |
| System touchpoints | `system_touchpoints` | count, capped at 10, normalized 0-1 | 0.20 |
| Failure mode risk | `failure_modes` | count, capped at 8, normalized 0-1 | 0.15 |
| Handoff gap presence | linked `ProcessHandoff.has_gap` | binary: 1 if any gap, 0 otherwise | 0.10 |

```
refinement = weighted_sum(signals)
```

#### Final base score

```
base_score = gate * 0.6 + refinement * 0.4
```

Range: 0.0–1.0. The gate provides a floor/ceiling based on feasibility; refinement differentiates within the feasible set.

### Scoring Logic

- NVA (Non-Value-Adding) processes score highest for refinement — pure waste, best candidates to eliminate
- The multiplicative gate means low automation potential + weak evidence always produces a low score, regardless of how wasteful or complex the process is
- Strong evidence is both a gate signal AND implied in other signals (high evidence → more accurate enrichment fields)
- System touchpoints and failure modes differentiate between "automate for efficiency" vs. "automate for risk reduction"

### Synthesized Candidate Scoring

For synthesized candidates, the gate averages across constituent processes. The refinement adds a **cross-process bonus** (0.05–0.15) based on the number of handoffs eliminated. Rationale: collapsing 3 processes with 2 handoff gaps into one workflow has compounding value beyond the individual process scores.

---

## Stage 3: LLM Independent Scoring + Narrative

### Anchoring-Free Design

Research on LLM calibration shows systematic anchoring bias — when provided a reference score, models make small perturbations around it regardless of qualitative merit. To produce a genuinely independent signal:

**The LLM does NOT receive `base_score`.** It receives only the process enrichment data (actors, triggers, decision logic, touchpoints, failure modes, evidence sources, value classification, complexity, narrative) and is asked to produce its own assessment.

### LLM responsibilities

1. **Independent qualitative score** (0.0–1.0) — the LLM assesses automation suitability based on factors the heuristic can't capture: organizational context inferred from the process descriptions, domain-specific automation patterns, implementation risk, and qualitative judgment about whether the process description actually describes something automatable.

2. **Automation type validation** — confirm or override the Stage 1 deterministic classification with rationale. The LLM can see nuance the decision tree misses (e.g., "the trigger is technically bounded but the real-world context requires judgment").

3. **Narrative generation** — 2-4 sentences explaining why this process is a strong automation candidate, what the workflow would look like, and what business outcome it drives. Written for a non-technical decision-maker.

4. **Auto-estimate financial assumptions** — based on the process enrichment (actors, frequency, duration, role types, system touchpoints, automation type), generate reasonable default values for `assumptions_json`. Use industry benchmarks embedded in the prompt:
   - Role-type salary ranges (sales_ops ~$70K, account_executive ~$110K, engineering ~$130K, etc.)
   - Frequency-to-hours mapping (daily + 3 actors + medium complexity ≈ 4-6 hrs/week)
   - `technology_cost` estimate based on system touchpoint count, complexity, and automation type
   - `hard_savings_pct` estimate — what fraction of savings are eliminable cost actions vs. freed capacity
   - `annual_operational_cost` — based on automation type and estimated execution volume

5. **Recommended actions** — populate `actions_json` with 3-5 concrete implementation steps.

### Output per candidate

```json
{
  "llm_score": 0.78,
  "score_rationale": "Strong candidate despite medium complexity — the 4 system touchpoints are all Salesforce-native, reducing integration risk. The decision logic is entirely rule-based (BANT criteria), making this suitable for deterministic automation with agentic exception handling.",
  "automation_type_override": null,
  "automation_type_rationale": "Confirmed hybrid — core scoring is deterministic but edge cases (competitor mentions, unusual company structures) need LLM judgment.",
  "narrative": "Lead qualification currently involves 3 AEs manually scoring leads against BANT criteria across Salesforce and HubSpot. A hybrid workflow could automate 80% of scoring deterministically, route qualified leads to the right AE, and flag ambiguous cases for human review — eliminating ~4.5 hours/week of manual work per rep.",
  "assumptions": {
    "fte_annual_cost": 110000,
    "hours_per_week": 4.5,
    "frequency": "daily",
    "actor_count": 3,
    "role_type": "account_executive",
    "technology_cost": 18000,
    "change_management_factor": 0.35,
    "annual_operational_cost": 3600,
    "adoption_ramp": [0.1, 0.5, 0.85, 0.95, 1.0],
    "productivity_dip": 0.04,
    "efficiency_gain": 0.72,
    "hard_savings_pct": 0.25,
    "discount_rate": 0.10
  },
  "actions": [
    {"step": 1, "action": "Define BANT scoring criteria as deterministic rules in Agentforce", "effort": "low"},
    {"step": 2, "action": "Build routing logic as Apex action", "effort": "medium"},
    {"step": 3, "action": "Create HubSpot sync flow with exception handling agent", "effort": "medium"},
    {"step": 4, "action": "Pilot with one AE team for 2 weeks", "effort": "low"},
    {"step": 5, "action": "Roll out org-wide with monitoring dashboard", "effort": "low"}
  ]
}
```

### Composite score (blending)

```
composite_score = base_score * 0.7 + llm_score * 0.3
```

Clamped to [0.0, 1.0]. The heuristic dominates because it's deterministic and auditable. The LLM contributes qualitative nuance.

### Divergence detection

```
divergence = abs(base_score - llm_score)
score_divergence_flag = divergence > 0.25
```

When the heuristic and LLM disagree significantly, the recommendation is flagged for human review. The disagreement itself is informative — it means either the data doesn't tell the full story (heuristic high, LLM low) or there's qualitative value the data misses (heuristic low, LLM high). Both are worth investigating.

All three scores (`base_score`, `llm_score`, `composite_score`) and the divergence flag are stored on the `Recommendation` row for full auditability.

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
def compute_projections(assumptions: dict) -> dict:
    """Returns scenarios_json with annual_savings, hard/soft split,
    headcount_deflection, NPV, and payback per scenario for 5 years."""
```

#### Resolve assumptions

```python
def resolve(assumptions: dict, key: str) -> float:
    """Return override if present, else original value."""
    overrides = assumptions.get("overrides", {})
    return overrides.get(key, assumptions.get(key))
```

#### Total investment (Year 0 cost)

```
technology_cost = resolve("technology_cost")
change_management_factor = resolve("change_management_factor")  # default 0.4
total_investment = technology_cost * (1 + change_management_factor)
```

Research: hidden costs (training, process redesign, organizational learning, parallel running) account for 40–60% of total technology investment. The `change_management_factor` at 0.4 captures the low end. Chat enrichment can refine this.

#### Base savings (annual at full adoption)

```
base_savings = fte_annual_cost * (hours_per_week / 40) * actor_count * efficiency_gain
```

#### Ongoing operational cost

```
annual_operational_cost = resolve("annual_operational_cost")
```

Auto-estimated by automation type:
- **Deterministic:** ~$1,200/year (infrastructure, monitoring, maintenance)
- **Agentic:** `estimated_executions_per_month * cost_per_execution * 12` (e.g., 500 exec/month * $0.15 * 12 = $10,800/year)
- **Hybrid:** `deterministic_base + (agentic_fraction * agentic_cost)` (e.g., $1,200 + 0.2 * $10,800 = $3,360/year)

#### Per-year calculation (with J-Curve)

```
for n in 0..4:
    adoption = adoption_ramp[n] * multiplier
    gross_savings = base_savings * adoption
    
    if n == 0:
        # J-Curve: productivity dip + investment hit
        j_curve_drag = base_savings * productivity_dip
        year_savings = gross_savings - j_curve_drag - total_investment / multiplier - annual_operational_cost
    else:
        year_savings = gross_savings - annual_operational_cost
    
    hard_savings[n] = year_savings * hard_savings_pct
    soft_savings[n] = year_savings * (1 - hard_savings_pct)
    headcount_deflection[n] = max(0, gross_savings / fte_annual_cost)
    
    cumulative[n] = cumulative[n-1] + year_savings
    discounted[n] = year_savings / (1 + discount_rate) ** n
```

#### NPV

```
npv = sum(discounted[0..4])
```

This is what finance uses for go/no-go decisions. Shows the present value of all future savings minus investment, discounted at the org's cost of capital.

#### Headcount deflection

```
headcount_deflection[n] = max(0, (base_savings * adoption_ramp[n]) / fte_annual_cost)
```

Not "people fired" — future hires not needed as the org scales. Always >= 0 (doesn't go negative even when Year 0 net savings are negative, because the deflection represents capacity freed, not P&L impact).

#### Three scenarios (sensitivity analysis)

| Scenario | Multiplier | Meaning |
|----------|-----------|---------|
| Optimistic | 1.3 | Higher efficiency, faster adoption, lower investment |
| Expected | 1.0 | Values as estimated or overridden |
| Conservative | 0.7 | Lower efficiency, slower adoption, higher investment |

The multiplier applies to `efficiency_gain` and `adoption_ramp` values, and inversely to `total_investment` and `annual_operational_cost`. This is **sensitivity analysis** (same model, three parameter sets), not Monte Carlo simulation. The naming is intentional — avoids false precision while communicating uncertainty range effectively.

#### Payback period (per scenario)

```
payback_month = first month where cumulative_savings > 0
```

Finance prioritizes payback over ROI because it reflects liquidity reality and timing risk. Showing payback per scenario communicates implementation risk: "expected payback is 16 months, but if things go well it's 8, if poorly it's 28."

#### Portfolio aggregation

```
portfolio_year_n[scenario] = sum(rec.scenarios[scenario].annual_savings[n] for rec in selected)
portfolio_npv[scenario] = sum(rec.scenarios.npv[scenario] for rec in selected)
```

Each recommendation is independent. No interaction effects in v1.

---

## Chat Enrichment

### Anchor type: `recommendation`

When a chat thread opens with `anchor_type: recommendation`, the system prompt includes:
- The recommendation's title, narrative, scoring breakdown, current assumptions, and current projections
- The hard/soft savings split and which assumptions drive each
- Linked processes' names, descriptions, and key enrichment fields
- Role instruction: focus on refining financial assumptions, ask targeted questions, call update tools when the user provides information
- Specific guidance: prioritize surfacing hard savings ("Would automating this eliminate any current spend — contractors, tool licenses, overtime?") because hard savings are what survive CFO scrutiny

This is a distinct prompt profile from the discovery chat (which instructs the model NOT to give recommendations).

### Chat tools

**Read-only (auto-execute):**
- `get_recommendation_details` — full recommendation with assumptions, projections, and hard/soft split
- `get_process_context` — linked process enrichment data
- `get_scoring_breakdown` — heuristic gate/refinement values, LLM score, divergence flag

**Write (proposed action, user confirms):**
- `update_assumption` — updates fields in `assumptions_json.overrides`, triggers financial engine recalc, appends to `enrichment_log`, returns updated projections with NPV impact

### Conversation behavior

The LLM identifies which assumptions are weakest (auto-estimated vs. user-confirmed) and most impactful (which move the NPV needle most), then prioritizes questions accordingly. It specifically probes for:

1. **Hard savings opportunities** — the auto-estimate defaults to 30% hard savings, but the user may know about eliminable contractor spend, tool licenses, or positions that won't be backfilled
2. **Actor count and time accuracy** — research shows employees underestimate task time by 35%+; the LLM should ask for real measurements, not estimates
3. **Automation type validation** — "We classified this as hybrid — does that feel right? Is the core logic really rule-based, or is there more judgment involved than the data suggests?"

When the user provides information, the LLM immediately calls `update_assumption` and reports the impact on NPV and payback period.

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
| `GET` | `/recommendations/{id}` | Response includes new fields (scenarios, assumptions, scoring breakdown, automation type) |
| `GET` | `/recommendations/` | Filterable by `recommendation_type` and `automation_type`, sortable by `composite_score` or `estimated_roi` |

### Recalculate request/response

```
POST /recommendations/{id}/recalculate
Body: { "overrides": { "fte_annual_cost": 95000, "actor_count": 5 } }

Response: full Recommendation with updated scenarios_json (including NPV, hard/soft split), estimated_roi, enrichment_log
```

### Portfolio projection request/response

```
POST /recommendations/portfolio-projection
Body: { "recommendation_ids": ["uuid1", "uuid2", ...], "global_overrides": {} }

Response: {
  "optimistic": { "annual_savings": [...], "cumulative": [...], "hard_savings": [...], "soft_savings": [...], "headcount_deflection": [...] },
  "expected": { ... },
  "conservative": { ... },
  "npv": { "optimistic": 540000, "expected": 380000, "conservative": 190000 },
  "total_payback_month": { "optimistic": 6, "expected": 12, "conservative": 22 },
  "recommendation_count": 4,
  "by_automation_type": { "deterministic": 1, "agentic": 1, "hybrid": 2 }
}
```

---

## Frontend: Portfolio View & Value Dashboard

### Page structure (3 zones)

**Zone 1: Portfolio Value Dashboard (top)**
- 5-year value curve (Recharts area chart): three lines for optimistic/expected/conservative, confidence band shaded between optimistic and conservative
- **Hard/soft savings toggle** — stacked area showing hard savings (solid) vs. soft savings (translucent) within each scenario line. Default view shows total; toggle splits them. This is critical for CFO conversations.
- Key numbers: **5-year NPV (expected)**, total Year 5 headcount deflection, **expected payback period**, count of selected recommendations, automation type breakdown (N deterministic, N agentic, N hybrid)
- Updates live as recommendations are toggled in/out from Zone 3

**Zone 2: Recommendation Detail (expandable on click)**
- **Automation type badge** — prominent tag: "Deterministic", "Agentic", or "Hybrid" with a one-line explanation
- Scoring breakdown: horizontal bar chart showing gate signals (automation potential, evidence) and refinement signals separately, plus LLM score. If `score_divergence_flag` is true, show a warning: "Heuristic and AI assessment disagree — review recommended"
- Narrative: the LLM-generated justification
- Assumptions table: shows auto-estimated values (tagged), user-overridden values (highlighted). Hard vs. soft savings split visible. Inline editing or "Refine" button for chat.
- Individual value curve: same 3-scenario chart for this single recommendation, with NPV and payback prominently displayed
- Linked processes: clickable links to process tree / domain map
- Actions: "Refine Assumptions" (opens chat), "Accept" (status change), "Dismiss"

**Zone 3: Recommendation List (cards)**
- Each card: title, `recommendation_type` tag (discovered / synthesized), `automation_type` tag, composite score, expected 5-year NPV, category, priority
- **Divergence indicator** — small icon when heuristic and LLM scores disagree
- Checkbox on each card: toggles inclusion in portfolio dashboard
- Sort/filter by: score, NPV, category, type, automation type, status
- Tabs: Active / Accepted / Dismissed

### Agent scaffold stub

Accepted recommendations get a "Generate Agent" button (visible, marked as coming soon). On click:
- Create `Agent` row with `linked_recommendation_id`
- Set `status = 'pending_generation'`
- Populate `config_json` with the recommendation's linked processes, assumptions, actions, and `automation_type`
- This is the handoff interface for the future AgentScript generator pipeline

### Real-time updates

When chat updates an assumption via `update_assumption`, the frontend invalidates the TanStack Query cache for that recommendation. The portfolio dashboard re-fetches and Recharts re-renders. No websocket needed — the chat action completes synchronously, the mutation's `onSuccess` triggers cache invalidation.

---

## Antipatterns to Watch

These are failure modes identified through research that the implementation must actively guard against.

### 1. The False Precision Trap

**Risk:** Showing "$182,347 in 5-year savings" when the real answer is "roughly $150K–$200K." Auto-estimated assumptions have wide uncertainty bands, and presenting precise numbers implies confidence we don't have.

**Mitigation:** Always show ranges (the three scenarios), never a single number in isolation. The UI should lead with the range ("$52K–$188K NPV") and show the expected case as the midpoint, not the headline. Format large numbers to appropriate precision ($182K, not $182,347).

### 2. Soft Savings Passed Off as Hard

**Risk:** A recommendation shows $500K in savings, the executive approves, and finance rejects it because it's all "freed capacity" with no line-item cost reduction. This destroys credibility for all future recommendations.

**Mitigation:** The hard/soft split is explicit in every projection. The chat enrichment specifically probes for hard savings. The portfolio dashboard can filter by "hard savings only" for the CFO audience. Never default `hard_savings_pct` above 0.3 without user confirmation.

### 3. Anchoring the LLM

**Risk:** If the LLM sees the heuristic score, it anchors to it and makes trivial adjustments. The "independent signal" value is lost.

**Mitigation:** Stage 3 prompt explicitly omits `base_score`. The LLM receives enrichment data only. Blending happens in code after both scores are computed. The divergence flag catches cases where the two signals genuinely disagree.

### 4. Agentic Overkill

**Risk:** Recommending agentic AI for processes that are purely rule-based. 62% of failed AI automation projects made this mistake. The financial model looks good because agentic sounds impressive, but implementation fails or costs spiral.

**Mitigation:** The `automation_type` classification is a first-class concept, not an afterthought. Deterministic candidates are explicitly surfaced as "automate with rules, no AI needed." The financial model reflects the cost difference. The UI communicates this distinction prominently.

### 5. J-Curve Denial

**Risk:** Showing positive ROI from Day 1. Decision-makers approve based on the model, then lose confidence when Year 0 is actually negative. The credibility of the entire platform is damaged.

**Mitigation:** Year 0 is honestly negative in all scenarios. The J-Curve is visible on the chart. The payback period is per-scenario so the worst case is visible. The chat enrichment can probe for realistic change management timelines.

### 6. Score Gaming via Weight Sensitivity

**Risk:** Small changes to the heuristic weights produce dramatically different rankings, making the scoring feel arbitrary.

**Mitigation:** The multiplicative gate provides stability — it's hard to game because both gate signals must be strong. The weights on refinement signals are less sensitive because they only affect differentiation within the feasible set, not whether something is recommended at all. Store the weights used in `RecommendationRun.config` so they're versioned.

### 7. Eval Drift

**Risk:** The LLM's scoring behavior drifts over time as model providers update weights. 91% of ML models experience performance degradation. Yesterday's scores aren't comparable to today's.

**Mitigation:** Store the model identifier in `RecommendationRun.config`. Log LLM scores in Langfuse with the recommendation run context. Track score distributions across runs — if the LLM's average score shifts significantly between runs with similar input data, flag it. Consider pinning to a specific model version for scoring consistency.

---

## Out of Scope (future work)

- **AgentScript generation** — the pipeline that consumes accepted recommendations and produces Salesforce AgentScript, Apex actions, and React components. Stubbed with the `Agent` model handoff.
- **Historical comparison** — comparing recommendation runs over time to show progress.
- **Interaction effects** — portfolio-level synergies or conflicts between recommendations (e.g., shared implementation costs, adoption curve dependencies).
- **Automated re-scoring** — re-running the LLM stages when discovery is re-run. Currently manual.
- **Org research integration** — feeding `OrgResearchProfile` (industry, company size, growth rate) into the financial assumptions. Natural enrichment source for salary benchmarks and scaling factors.
- **Full Monte Carlo** — replacing the three-scenario sensitivity analysis with proper stochastic simulation using probability distributions on each input variable. The current approach is sufficient for v1 but understates tail risk.
- **Per-assumption sensitivity analysis** — tornado charts showing which individual assumptions move the NPV needle most. Currently implicit in the chat's prioritization logic but not visualized.
