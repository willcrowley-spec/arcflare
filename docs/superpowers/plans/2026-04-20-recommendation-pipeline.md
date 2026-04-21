# Recommendation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the recommendation pipeline from the [design spec](../specs/2026-04-20-recommendation-pipeline-design.md) — scoring, financial projections, chat enrichment, and portfolio UI.

**Architecture:** Split-brain: Celery pipeline (candidate generation + heuristic scoring + LLM scoring/narrative) produces Recommendation rows; a decoupled Financial Engine (pure math, no LLM) computes sensitivity projections and is callable from both the pipeline and the API for live recalc.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Celery/Redis, LiteLLM, Langfuse, React 18, TanStack Query, Recharts, Tailwind 4

---

## File Structure

### Backend — New files
- `backend/alembic/versions/025_recommendation_pipeline.py` — migration
- `backend/app/models/recommendation_run.py` — RecommendationRun model
- `backend/app/services/recommendations/financial_engine.py` — pure math projections
- `backend/app/services/recommendations/heuristic_scorer.py` — gate + refinement scoring
- `backend/app/services/recommendations/candidate_generator.py` — Stage 1: query processes, classify automation type
- `backend/app/services/recommendations/llm_scorer.py` — Stage 3: independent LLM scoring + narrative
- `backend/app/services/recommendations/pipeline.py` — orchestrator: chains stages, persists results
- `backend/app/services/chat/tools/recommendation_tools.py` — chat tool definitions for enrichment

### Backend — Modified files
- `backend/app/models/recommendation.py` — add new columns
- `backend/app/models/__init__.py` — register RecommendationRun
- `backend/app/schemas/recommendation.py` — expanded response schemas
- `backend/app/api/routes/recommendations.py` — new endpoints
- `backend/app/workers/analysis.py` — rewire to new pipeline
- `backend/app/workers/celery_app.py` — register new task
- `backend/app/services/chat/context.py` — add recommendation anchor
- `backend/app/services/chat/tools.py` — register recommendation tools

### Frontend — New files
- `frontend/src/pages/Recommendations/PortfolioDashboard.tsx` — Zone 1: value curve + KPIs
- `frontend/src/pages/Recommendations/RecommendationDetail.tsx` — Zone 2: expandable detail
- `frontend/src/pages/Recommendations/RecommendationCard.tsx` — Zone 3: card component
- `frontend/src/pages/Recommendations/ValueChart.tsx` — shared Recharts area chart
- `frontend/src/pages/Recommendations/ScoringBreakdown.tsx` — horizontal bar chart
- `frontend/src/pages/Recommendations/usePortfolio.ts` — portfolio selection state + projection query

### Frontend — Modified files
- `frontend/src/pages/Recommendations/index.tsx` — full rewrite to 3-zone layout
- `frontend/src/hooks/useApi.ts` — add new query/mutation hooks

---

### Task 1: Data Model — RecommendationRun + Recommendation Columns + Migration

**Files:**
- Create: `backend/app/models/recommendation_run.py`
- Modify: `backend/app/models/recommendation.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/025_recommendation_pipeline.py`

- [ ] **Step 1: Create RecommendationRun model**

Create `backend/app/models/recommendation_run.py`:

```python
"""Recommendation pipeline run tracking."""
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    stage_results: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
```

- [ ] **Step 2: Add new columns to Recommendation model**

In `backend/app/models/recommendation.py`, add these columns after the existing `linked_process_ids` column:

```python
    recommendation_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="discovered"
    )
    automation_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="hybrid"
    )
    base_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_divergence_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    assumptions_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scenarios_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    enrichment_log: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    recommendation_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
```

Add `Boolean` and `Text` to the existing SQLAlchemy imports if not already present (Text is already imported; add Boolean).

- [ ] **Step 3: Register RecommendationRun in models __init__.py**

In `backend/app/models/__init__.py`, add import and __all__ entry for `RecommendationRun`.

- [ ] **Step 4: Create Alembic migration**

Create `backend/alembic/versions/025_recommendation_pipeline.py`. Use the DiscoveryRun migration pattern. The migration must:

1. Create `recommendation_runs` table
2. Add all new columns to `recommendations` table
3. Handle downgrade (drop columns, drop table)

Look at an existing migration for the exact revision chain (down_revision should be the latest existing migration's revision ID). Run: `cd backend && alembic heads` to find the current head.

- [ ] **Step 5: Verify migration runs**

Run: `cd backend && alembic upgrade head`
Expected: migration applies without errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/recommendation_run.py backend/app/models/recommendation.py backend/app/models/__init__.py backend/alembic/versions/025_recommendation_pipeline.py
git commit -m "feat: recommendation pipeline data model + migration"
```

---

### Task 2: Financial Engine

**Files:**
- Create: `backend/app/services/recommendations/financial_engine.py`

This is a **pure function module** — no DB, no LLM, no imports from the app layer except types. Fully testable in isolation.

- [ ] **Step 1: Create the financial engine module**

Create `backend/app/services/recommendations/financial_engine.py`:

```python
"""Pure-math financial projection engine for recommendations.

Stateless module — takes an assumptions dict and returns sensitivity analysis
projections. Called by the pipeline after scoring and by the API for live
recalc when chat enrichment updates assumptions.

No LLM, no DB access, no app imports beyond typing.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SCENARIO_MULTIPLIERS = {"optimistic": 1.3, "expected": 1.0, "conservative": 0.7}
DEFAULT_PROJECTION_YEARS = 5


def resolve_assumption(assumptions: dict, key: str) -> Any:
    overrides = assumptions.get("overrides", {})
    if key in overrides:
        return overrides[key]
    return assumptions.get(key)


def compute_total_investment(assumptions: dict) -> float:
    tech_cost = float(resolve_assumption(assumptions, "technology_cost") or 0)
    cm_factor = float(resolve_assumption(assumptions, "change_management_factor") or 0.4)
    return tech_cost * (1 + cm_factor)


def compute_base_savings(assumptions: dict) -> float:
    fte_cost = float(resolve_assumption(assumptions, "fte_annual_cost") or 0)
    hours = float(resolve_assumption(assumptions, "hours_per_week") or 0)
    actors = float(resolve_assumption(assumptions, "actor_count") or 1)
    efficiency = float(resolve_assumption(assumptions, "efficiency_gain") or 0)
    return fte_cost * (hours / 40) * actors * efficiency


def compute_scenario(
    assumptions: dict,
    multiplier: float,
    years: int = DEFAULT_PROJECTION_YEARS,
) -> dict:
    base_savings = compute_base_savings(assumptions)
    total_investment = compute_total_investment(assumptions)
    annual_op_cost = float(resolve_assumption(assumptions, "annual_operational_cost") or 0)
    ramp = resolve_assumption(assumptions, "adoption_ramp") or [0.1, 0.5, 0.85, 0.95, 1.0]
    productivity_dip = float(resolve_assumption(assumptions, "productivity_dip") or 0.05)
    hard_pct = float(resolve_assumption(assumptions, "hard_savings_pct") or 0.3)
    fte_cost = float(resolve_assumption(assumptions, "fte_annual_cost") or 1)
    discount_rate = float(resolve_assumption(assumptions, "discount_rate") or 0.10)

    annual_savings: list[float] = []
    cumulative: list[float] = []
    hard_savings: list[float] = []
    soft_savings: list[float] = []
    headcount_deflection: list[float] = []
    discounted: list[float] = []
    running_cumulative = 0.0

    for n in range(years):
        adoption = min(1.0, ramp[n] * multiplier) if n < len(ramp) else 1.0
        gross = base_savings * adoption

        if n == 0:
            j_curve_drag = base_savings * productivity_dip
            inv_hit = total_investment / multiplier
            op_cost = annual_op_cost / multiplier
            net = gross - j_curve_drag - inv_hit - op_cost
        else:
            op_cost = annual_op_cost / multiplier
            net = gross - op_cost

        annual_savings.append(round(net))
        running_cumulative += net
        cumulative.append(round(running_cumulative))
        hard_savings.append(round(net * hard_pct))
        soft_savings.append(round(net * (1 - hard_pct)))
        hc = max(0.0, gross / fte_cost) if fte_cost > 0 else 0.0
        headcount_deflection.append(round(hc, 2))
        disc = net / ((1 + discount_rate) ** n) if discount_rate > 0 else net
        discounted.append(disc)

    npv = round(sum(discounted))

    payback_month: int | None = None
    if total_investment > 0:
        monthly_increment = 0.0
        cum = 0.0
        for n in range(years):
            monthly_inc = annual_savings[n] / 12
            for m in range(12):
                cum += monthly_inc
                if cum >= 0 and payback_month is None:
                    payback_month = n * 12 + m + 1

    return {
        "annual_savings": annual_savings,
        "cumulative": cumulative,
        "hard_savings": hard_savings,
        "soft_savings": soft_savings,
        "headcount_deflection": headcount_deflection,
        "assumptions_multiplier": multiplier,
        "npv": npv,
        "payback_month": payback_month,
    }


def compute_projections(assumptions: dict) -> dict:
    scenarios = {}
    for name, mult in SCENARIO_MULTIPLIERS.items():
        scenarios[name] = compute_scenario(assumptions, mult)

    return {
        **scenarios,
        "npv": {name: scenarios[name]["npv"] for name in SCENARIO_MULTIPLIERS},
        "payback_month": {
            name: scenarios[name]["payback_month"] for name in SCENARIO_MULTIPLIERS
        },
        "computed_at": datetime.now(tz=UTC).isoformat(),
    }


def compute_portfolio_projections(
    recommendations_assumptions: list[dict],
    global_overrides: dict | None = None,
) -> dict:
    merged: list[dict] = []
    for a in recommendations_assumptions:
        if global_overrides:
            copy = dict(a)
            existing_overrides = dict(copy.get("overrides", {}))
            existing_overrides.update(global_overrides)
            copy["overrides"] = existing_overrides
            merged.append(copy)
        else:
            merged.append(a)

    individual = [compute_projections(a) for a in merged]

    years = DEFAULT_PROJECTION_YEARS
    portfolio: dict = {}
    for scenario_name in SCENARIO_MULTIPLIERS:
        agg: dict[str, list] = {
            "annual_savings": [0] * years,
            "cumulative": [0] * years,
            "hard_savings": [0] * years,
            "soft_savings": [0] * years,
            "headcount_deflection": [0.0] * years,
        }
        for proj in individual:
            s = proj[scenario_name]
            for y in range(years):
                agg["annual_savings"][y] += s["annual_savings"][y]
                agg["cumulative"][y] += s["cumulative"][y]
                agg["hard_savings"][y] += s["hard_savings"][y]
                agg["soft_savings"][y] += s["soft_savings"][y]
                agg["headcount_deflection"][y] += s["headcount_deflection"][y]
        portfolio[scenario_name] = agg

    return {
        **portfolio,
        "npv": {
            name: sum(p[name]["npv"] for p in individual) for name in SCENARIO_MULTIPLIERS
        },
        "payback_month": {
            name: max(
                (p[name]["payback_month"] or 0 for p in individual), default=None
            )
            for name in SCENARIO_MULTIPLIERS
        },
        "recommendation_count": len(individual),
    }
```

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from app.services.recommendations.financial_engine import compute_projections; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendations/financial_engine.py
git commit -m "feat: financial engine -- pure math projection module with sensitivity analysis"
```

---

### Task 3: Heuristic Scorer

**Files:**
- Create: `backend/app/services/recommendations/heuristic_scorer.py`

Pure function — takes process enrichment dicts, returns base scores. No DB, no LLM.

- [ ] **Step 1: Create heuristic scorer**

Create `backend/app/services/recommendations/heuristic_scorer.py`:

```python
"""Multiplicative gate + additive refinement scoring for recommendation candidates.

Pure function — takes process enrichment data and returns a base_score.
No DB, no LLM, no side effects.
"""
from __future__ import annotations

AUTOMATION_POTENTIAL_MAP = {"low": 0.15, "medium": 0.5, "high": 0.9}
VALUE_CLASSIFICATION_MAP = {"NVA": 0.9, "BVA": 0.6, "VA": 0.3}
COMPLEXITY_MAP = {"low": 0.9, "medium": 0.6, "high": 0.3}

EVIDENCE_CAP = 15
TOUCHPOINT_CAP = 10
FAILURE_MODE_CAP = 8

GATE_WEIGHT = 0.6
REFINEMENT_WEIGHT = 0.4


def _evidence_strength(evidence_sources: list[dict]) -> float:
    if not evidence_sources:
        return 0.1
    confidences = [e.get("confidence", 0.5) for e in evidence_sources]
    avg_conf = sum(confidences) / len(confidences)
    count_norm = min(len(evidence_sources) / EVIDENCE_CAP, 1.0)
    return max(0.1, count_norm * avg_conf)


def _normalize_count(count: int, cap: int) -> float:
    return min(count / cap, 1.0) if cap > 0 else 0.0


def score_process(process: dict) -> dict:
    """Score a single process for automation potential.

    Args:
        process: dict with keys matching BusinessProcess columns
            (automation_potential, value_classification, complexity_score,
             evidence_sources, system_touchpoints, failure_modes)
            Plus 'has_handoff_gap': bool from linked ProcessHandoff data.

    Returns:
        dict with base_score, gate_score, refinement_score, and signal breakdown.
    """
    auto_pot = AUTOMATION_POTENTIAL_MAP.get(
        (process.get("automation_potential") or "").lower(), 0.4
    )
    evidence = _evidence_strength(process.get("evidence_sources", []))
    gate = auto_pot * evidence

    value_class = VALUE_CLASSIFICATION_MAP.get(
        (process.get("value_classification") or "").upper(), 0.5
    )
    complexity_inv = COMPLEXITY_MAP.get(
        (process.get("complexity_score") or "").lower(), 0.5
    )
    touchpoints = _normalize_count(
        len(process.get("system_touchpoints", [])), TOUCHPOINT_CAP
    )
    failure_risk = _normalize_count(
        len(process.get("failure_modes", [])), FAILURE_MODE_CAP
    )
    has_gap = 1.0 if process.get("has_handoff_gap") else 0.0

    refinement = (
        value_class * 0.30
        + complexity_inv * 0.25
        + touchpoints * 0.20
        + failure_risk * 0.15
        + has_gap * 0.10
    )

    base_score = round(gate * GATE_WEIGHT + refinement * REFINEMENT_WEIGHT, 4)
    base_score = max(0.0, min(1.0, base_score))

    return {
        "base_score": base_score,
        "gate_score": round(gate, 4),
        "refinement_score": round(refinement, 4),
        "signals": {
            "automation_potential": round(auto_pot, 2),
            "evidence_strength": round(evidence, 2),
            "value_classification": round(value_class, 2),
            "complexity_inverse": round(complexity_inv, 2),
            "system_touchpoints": round(touchpoints, 2),
            "failure_mode_risk": round(failure_risk, 2),
            "handoff_gap": round(has_gap, 2),
        },
    }


def score_synthesized(
    constituent_processes: list[dict],
    eliminated_handoff_count: int = 0,
) -> dict:
    """Score a synthesized (cross-process composite) candidate.

    Averages gate signals across constituent processes and adds a
    cross-process bonus based on eliminated handoffs.
    """
    if not constituent_processes:
        return {"base_score": 0.0, "gate_score": 0.0, "refinement_score": 0.0, "signals": {}}

    individual_scores = [score_process(p) for p in constituent_processes]

    avg_gate = sum(s["gate_score"] for s in individual_scores) / len(individual_scores)
    avg_refinement = sum(s["refinement_score"] for s in individual_scores) / len(individual_scores)

    cross_process_bonus = min(0.15, eliminated_handoff_count * 0.05)

    base_score = round(
        avg_gate * GATE_WEIGHT + (avg_refinement + cross_process_bonus) * REFINEMENT_WEIGHT,
        4,
    )
    base_score = max(0.0, min(1.0, base_score))

    avg_signals = {}
    if individual_scores:
        for key in individual_scores[0]["signals"]:
            avg_signals[key] = round(
                sum(s["signals"][key] for s in individual_scores) / len(individual_scores), 2
            )
        avg_signals["cross_process_bonus"] = round(cross_process_bonus, 2)

    return {
        "base_score": base_score,
        "gate_score": round(avg_gate, 4),
        "refinement_score": round(avg_refinement + cross_process_bonus, 4),
        "signals": avg_signals,
    }
```

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from app.services.recommendations.heuristic_scorer import score_process; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendations/heuristic_scorer.py
git commit -m "feat: heuristic scorer -- multiplicative gate + additive refinement"
```

---

### Task 4: Candidate Generator + Automation Type Classifier

**Files:**
- Create: `backend/app/services/recommendations/candidate_generator.py`

Queries BusinessProcess rows from latest DiscoveryRun, filters, classifies automation type, and prepares candidate dicts for scoring.

- [ ] **Step 1: Create candidate generator**

Create `backend/app/services/recommendations/candidate_generator.py`. This module:

1. Queries all `BusinessProcess` rows for the org's latest completed `DiscoveryRun`
2. Filters out `automation_potential='low' AND value_classification='VA'` (null = include)
3. Classifies each as `deterministic`, `agentic`, or `hybrid` based on enrichment fields
4. Queries `ProcessHandoff` rows and marks which processes have gaps
5. Returns a list of candidate dicts ready for the heuristic scorer

The automation type classification uses a decision tree on `decision_logic`, `trigger_conditions`, `system_touchpoints`, and `failure_modes` — see the spec's Stage 1 section. Default to `hybrid` when signals are ambiguous.

The synthesized candidate generation is an LLM call — it sends all processes grouped by domain plus handoff data and asks for composite opportunities. Use the same `llm_call` pattern from `app.services.ai.router`.

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from app.services.recommendations.candidate_generator import generate_discovered_candidates; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendations/candidate_generator.py
git commit -m "feat: candidate generator with automation type classification"
```

---

### Task 5: LLM Scorer + Narrative Generator

**Files:**
- Create: `backend/app/services/recommendations/llm_scorer.py`

Stage 3 of the pipeline. Receives candidates with enrichment data (but NOT base_score — anti-anchoring). Returns independent LLM score, narrative, assumptions, and actions.

- [ ] **Step 1: Create LLM scorer**

Create `backend/app/services/recommendations/llm_scorer.py`. This module:

1. Takes a list of scored candidates (but the prompt only sends enrichment data, NOT base_score)
2. Batches candidates by domain for efficient LLM calls
3. Prompt asks the LLM to produce for each candidate: `llm_score` (0-1), `score_rationale`, `automation_type_override` (or null), `narrative`, `assumptions` dict, and `actions` list
4. Uses `llm_call` from `app.services.ai.router` with tier="strong"
5. Returns enriched candidates with LLM outputs merged in

Key: the prompt MUST NOT include the base_score — this prevents anchoring bias. Include only: process name, description, narrative, actors, triggers, decision logic, touchpoints, failure modes, evidence sources, value classification, complexity.

Use structured JSON output format matching the spec's Stage 3 output schema.

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from app.services.recommendations.llm_scorer import score_candidates_with_llm; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendations/llm_scorer.py
git commit -m "feat: LLM scorer with anti-anchoring design + narrative generation"
```

---

### Task 6: Pipeline Orchestrator + Celery Worker

**Files:**
- Create: `backend/app/services/recommendations/pipeline.py`
- Modify: `backend/app/workers/analysis.py`
- Modify: `backend/app/workers/celery_app.py`

Chains all stages together. Creates RecommendationRun, runs stages, persists results.

- [ ] **Step 1: Create pipeline orchestrator**

Create `backend/app/services/recommendations/pipeline.py`. This module:

1. Creates a `RecommendationRun` with status='running'
2. Calls `generate_discovered_candidates()` and `generate_synthesized_candidates()` (Stage 1)
3. Calls `score_process()` / `score_synthesized()` on each candidate (Stage 2)
4. Calls `score_candidates_with_llm()` (Stage 3)
5. Computes `composite_score = base_score * 0.7 + llm_score * 0.3` and `score_divergence_flag = abs(base_score - llm_score) > 0.25`
6. Deletes old pipeline-generated recs (preserving `status='accepted'`)
7. Creates `Recommendation` rows with all fields populated
8. Calls `compute_projections()` on each rec's assumptions and stores `scenarios_json`
9. Sets `estimated_roi` to the expected-case NPV
10. Updates `RecommendationRun` with stage_results and status='completed'

Each stage is wrapped in timing and logged to `stage_results`. Errors are caught and stored on the run.

- [ ] **Step 2: Rewire the Celery worker**

Replace the contents of `backend/app/workers/analysis.py` to call the new pipeline instead of the old analyzer+scorer. Keep the same task name for backward compatibility. Add Langfuse spans per stage.

- [ ] **Step 3: Register in celery_app if needed**

Check `backend/app/workers/celery_app.py` — the analysis module should already be included. Verify.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/recommendations/pipeline.py backend/app/workers/analysis.py
git commit -m "feat: recommendation pipeline orchestrator + rewired Celery worker"
```

---

### Task 7: Schemas + API Routes

**Files:**
- Modify: `backend/app/schemas/recommendation.py`
- Modify: `backend/app/api/routes/recommendations.py`

- [ ] **Step 1: Expand Pydantic schemas**

Update `backend/app/schemas/recommendation.py` to include all new fields in `RecommendationResponse`, add `RecalculateRequest`, `PortfolioProjectionRequest`, `PortfolioProjectionResponse`, `RecommendationRunResponse`, and update `RecommendationSummary` with new aggregations.

Key additions to `RecommendationResponse`: `recommendation_type`, `automation_type`, `base_score`, `llm_score`, `llm_rationale`, `score_divergence_flag`, `assumptions_json`, `scenarios_json`, `enrichment_log`, `recommendation_run_id`.

- [ ] **Step 2: Add new API endpoints**

In `backend/app/api/routes/recommendations.py`, add:

1. `POST /recommendations/{id}/recalculate` — takes `RecalculateRequest` (overrides dict), merges into assumptions_json.overrides, calls `compute_projections()`, updates rec, appends to enrichment_log, returns updated rec
2. `POST /recommendations/portfolio-projection` — takes list of rec IDs + optional global overrides, fetches assumptions, calls `compute_portfolio_projections()`, returns aggregated scenarios (does not persist)
3. `GET /recommendations/runs` — paginated list of RecommendationRun for org
4. `GET /recommendations/runs/{run_id}` — single run detail

Update existing endpoints:
- `GET /recommendations/` — add `recommendation_type` and `automation_type` filter params, add sort options
- `POST /recommendations/generate` — return the `RecommendationRun` ID

- [ ] **Step 3: Verify routes mount**

Run: `cd backend && python -c "from app.api.routes.recommendations import router; print(len(router.routes), 'routes')"`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/app/api/routes/recommendations.py
git commit -m "feat: recommendation API -- recalculate, portfolio projection, runs endpoints"
```

---

### Task 8: Chat Enrichment Integration

**Files:**
- Create: `backend/app/services/chat/tools/recommendation_tools.py`
- Modify: `backend/app/services/chat/context.py`
- Modify: `backend/app/services/chat/tools.py`

- [ ] **Step 1: Create recommendation chat tools**

Create `backend/app/services/chat/tools/recommendation_tools.py` with three tools:

1. `get_recommendation_details` (auto_execute=True) — fetches full rec with assumptions and projections
2. `get_scoring_breakdown` (auto_execute=True) — returns heuristic signals, LLM score, divergence
3. `update_assumption` (auto_execute=False, requires confirmation) — updates overrides, runs financial engine, appends enrichment_log, returns updated projections with NPV impact

Each tool follows the existing pattern in `app/services/chat/tools.py` — dict with `name`, `description`, `parameters`, `handler`, `auto_execute`.

- [ ] **Step 2: Add recommendation anchor context**

In `backend/app/services/chat/context.py`, add a `recommendation` case to `_anchor_context()`. When `anchor_type='recommendation'`:
- Load the Recommendation by ID
- Load linked BusinessProcess rows
- Build a system prompt section with: title, narrative, scoring breakdown, current assumptions, current projections, hard/soft split
- Override the default "don't give recommendations" instruction with the enrichment-focused persona from the spec

- [ ] **Step 3: Register tools in TOOL_REGISTRY**

In `backend/app/services/chat/tools.py`, import and register the three new tools. They should only be available when the thread has `anchor_type='recommendation'`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat/tools/recommendation_tools.py backend/app/services/chat/context.py backend/app/services/chat/tools.py
git commit -m "feat: chat enrichment for recommendations -- tools + anchor context"
```

---

### Task 9: Frontend — Value Chart + Scoring Breakdown Components

**Files:**
- Create: `frontend/src/pages/Recommendations/ValueChart.tsx`
- Create: `frontend/src/pages/Recommendations/ScoringBreakdown.tsx`

Shared components used by both the portfolio dashboard and recommendation detail.

- [ ] **Step 1: Create ValueChart component**

Create `frontend/src/pages/Recommendations/ValueChart.tsx` — a Recharts `AreaChart` that takes `scenarios_json` and renders:
- Three lines (optimistic / expected / conservative)
- Shaded confidence band between optimistic and conservative
- X-axis: Year 0-4, Y-axis: cumulative savings
- Optional hard/soft toggle (stacked areas within each line)
- Responsive, Tailwind-styled

Props: `scenarios: ScenariosJson`, `showHardSoftSplit?: boolean`, `height?: number`

- [ ] **Step 2: Create ScoringBreakdown component**

Create `frontend/src/pages/Recommendations/ScoringBreakdown.tsx` — horizontal bar chart showing:
- Gate signals (automation potential, evidence strength) with their scores
- Refinement signals (value class, complexity, touchpoints, failure modes, gaps) with weighted scores
- LLM score as a separate bar
- Divergence warning if `score_divergence_flag` is true

Props: `signals: Record<string, number>`, `baseScore: number`, `llmScore: number`, `divergenceFlag: boolean`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Recommendations/ValueChart.tsx frontend/src/pages/Recommendations/ScoringBreakdown.tsx
git commit -m "feat: ValueChart and ScoringBreakdown shared components"
```

---

### Task 10: Frontend — Portfolio Dashboard (Zone 1)

**Files:**
- Create: `frontend/src/pages/Recommendations/PortfolioDashboard.tsx`
- Create: `frontend/src/pages/Recommendations/usePortfolio.ts`

- [ ] **Step 1: Create usePortfolio hook**

Create `frontend/src/pages/Recommendations/usePortfolio.ts` — manages:
- `selectedIds: Set<string>` (which recs are included in portfolio)
- `toggle(id)`, `selectAll()`, `clearAll()`
- A TanStack Query mutation that calls `POST /recommendations/portfolio-projection` with the selected IDs
- Auto-refetches when selectedIds change (debounced 300ms)

- [ ] **Step 2: Create PortfolioDashboard component**

Create `frontend/src/pages/Recommendations/PortfolioDashboard.tsx` — Zone 1:
- Uses `usePortfolio` for data
- Renders `ValueChart` with aggregate scenarios
- Shows KPIs: 5-year NPV (expected), Year 5 headcount deflection, expected payback period, count selected, automation type breakdown
- Hard/soft savings toggle

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Recommendations/usePortfolio.ts frontend/src/pages/Recommendations/PortfolioDashboard.tsx
git commit -m "feat: portfolio dashboard with aggregate value projections"
```

---

### Task 11: Frontend — Recommendation Detail + Card Components (Zones 2 & 3)

**Files:**
- Create: `frontend/src/pages/Recommendations/RecommendationDetail.tsx`
- Create: `frontend/src/pages/Recommendations/RecommendationCard.tsx`

- [ ] **Step 1: Create RecommendationCard component**

Create `frontend/src/pages/Recommendations/RecommendationCard.tsx` — Zone 3 card:
- Title, recommendation_type tag (discovered/synthesized), automation_type tag (deterministic/agentic/hybrid)
- Composite score, 5-year NPV, category, priority
- Checkbox for portfolio inclusion (calls `usePortfolio.toggle`)
- Divergence indicator if flagged
- Click expands to Zone 2 detail

- [ ] **Step 2: Create RecommendationDetail component**

Create `frontend/src/pages/Recommendations/RecommendationDetail.tsx` — Zone 2 expandable:
- Automation type badge with explanation
- `ScoringBreakdown` component
- LLM narrative
- Assumptions table (auto-estimated tagged, overrides highlighted)
- Individual `ValueChart` for this rec
- Linked processes (clickable)
- Action buttons: "Refine Assumptions" (opens `openContextualChat`), "Accept", "Dismiss"
- "Generate Agent" button stub (visible, disabled, marked coming soon) — on accept, creates Agent row via API

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Recommendations/RecommendationCard.tsx frontend/src/pages/Recommendations/RecommendationDetail.tsx
git commit -m "feat: recommendation card and detail components"
```

---

### Task 12: Frontend — Recommendations Page Rewrite + API Hooks

**Files:**
- Modify: `frontend/src/pages/Recommendations/index.tsx`
- Modify: `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Add API hooks**

In `frontend/src/hooks/useApi.ts`, add hooks:
- `useRecalculateRecommendation()` — mutation: `POST /recommendations/{id}/recalculate`
- `usePortfolioProjection()` — mutation: `POST /recommendations/portfolio-projection`
- `useRecommendationRuns()` — query: `GET /recommendations/runs`

Update `useRecommendations` to accept `recommendation_type`, `automation_type`, and `sort` params.

- [ ] **Step 2: Rewrite Recommendations page**

Replace `frontend/src/pages/Recommendations/index.tsx` with the 3-zone layout:
- Zone 1: `PortfolioDashboard` (top)
- Zone 2: `RecommendationDetail` (expandable, shown when a card is clicked)
- Zone 3: Recommendation list using `RecommendationCard` components
- Tabs: Active / Accepted / Dismissed
- Sort/filter controls: by score, NPV, category, type, automation type
- Search bar (existing)
- Generate button (existing, triggers pipeline)

Wire up the `usePortfolio` hook to connect Zone 1 and Zone 3.

- [ ] **Step 3: Verify page renders**

Start dev server if not running. Navigate to /recommendations. Verify the page renders without errors (may show empty state if no data).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Recommendations/index.tsx frontend/src/hooks/useApi.ts
git commit -m "feat: recommendations page rewrite -- 3-zone portfolio layout"
```

---

## Dependency Graph

```
Task 1 (data model) ─┬─→ Task 4 (candidate gen)  ─┬─→ Task 6 (pipeline) ─→ Task 8 (chat)
                      ├─→ Task 7 (API routes)      │
Task 2 (financial)  ──┤                             │
Task 3 (heuristic)  ──┴─→ Task 5 (LLM scorer)    ──┘
                                                      Task 9  (charts) ─┬─→ Task 12 (page)
                                                      Task 10 (portfolio)┤
                                                      Task 11 (cards)   ─┘
```

**Parallel batch 1:** Tasks 1, 2, 3, 9 (completely independent)
**Parallel batch 2:** Tasks 4, 5, 7, 10, 11 (depend on batch 1)
**Sequential:** Task 6 (depends on 4, 5), Task 8 (depends on 6, 7), Task 12 (depends on 9, 10, 11)
