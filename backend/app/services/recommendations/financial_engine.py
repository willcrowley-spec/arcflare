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

_DEFAULT_RAMP = [0.1, 0.5, 0.85, 0.95, 1.0]

# When the LLM returns thin assumptions, fill gaps from automation class so
# projections are directionally meaningful instead of all zeros.
_DEFAULTS_BY_TYPE: dict[str, dict[str, Any]] = {
    "deterministic": {
        "fte_annual_cost": 75000,
        "technology_cost": 12000,
        "change_management_factor": 0.25,
        "efficiency_gain": 0.7,
        "hard_savings_pct": 0.8,
        "annual_operational_cost": 2000,
        "hours_per_week": 10,
        "actor_count": 2,
        "productivity_dip": 0.04,
        "discount_rate": 0.10,
        "adoption_ramp": list(_DEFAULT_RAMP),
    },
    "agentic": {
        "fte_annual_cost": 95000,
        "technology_cost": 35000,
        "change_management_factor": 0.40,
        "efficiency_gain": 0.4,
        "hard_savings_pct": 0.3,
        "annual_operational_cost": 8000,
        "hours_per_week": 20,
        "actor_count": 3,
        "productivity_dip": 0.08,
        "discount_rate": 0.10,
        "adoption_ramp": list(_DEFAULT_RAMP),
    },
    "hybrid": {
        "fte_annual_cost": 85000,
        "technology_cost": 20000,
        "change_management_factor": 0.30,
        "efficiency_gain": 0.5,
        "hard_savings_pct": 0.5,
        "annual_operational_cost": 5000,
        "hours_per_week": 15,
        "actor_count": 2,
        "productivity_dip": 0.06,
        "discount_rate": 0.10,
        "adoption_ramp": list(_DEFAULT_RAMP),
    },
}


def _norm_automation_type_for_engine(value: object | None) -> str:
    s = (str(value).strip().lower() if value is not None else "") or "hybrid"
    if s in _DEFAULTS_BY_TYPE:
        return s
    return "hybrid"


def _assumptions_with_type_defaults(
    assumptions: dict, automation_type: str | None
) -> dict:
    t = _norm_automation_type_for_engine(automation_type)
    defaults = _DEFAULTS_BY_TYPE[t]
    out = dict(assumptions)
    for key, val in defaults.items():
        if key not in out or out[key] is None:
            out[key] = list(val) if key == "adoption_ramp" and isinstance(val, list) else val
    return out


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
            net = gross - j_curve_drag - total_investment - annual_op_cost
        else:
            net = gross - annual_op_cost

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


def compute_projections(
    assumptions: dict, automation_type: str | None = None
) -> dict:
    merged = _assumptions_with_type_defaults(assumptions, automation_type)
    scenarios = {}
    for name, mult in SCENARIO_MULTIPLIERS.items():
        scenarios[name] = compute_scenario(merged, mult)

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
