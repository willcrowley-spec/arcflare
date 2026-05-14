"""Central recomputation boundary for recommendation financials and ARC Score."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.recommendation import Recommendation
from app.services.recommendations.arc_score import apply_arc_score
from app.services.recommendations.financial_assumptions import build_financial_assumptions
from app.services.recommendations.financial_engine import compute_projections


def _merge_overrides(assumptions: dict, overrides: dict[str, Any] | None) -> dict:
    if not overrides:
        return assumptions
    merged = dict(assumptions)
    existing = merged.get("overrides") if isinstance(merged.get("overrides"), dict) else {}
    next_overrides = dict(existing)
    next_overrides.update(overrides)
    merged["overrides"] = next_overrides
    return merged


def _existing_assumptions(rec: Recommendation) -> dict:
    return dict(rec.assumptions_json) if isinstance(rec.assumptions_json, dict) else {}


def build_recommendation_assumptions(
    rec: Recommendation,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict | None:
    existing = _existing_assumptions(rec)
    opp = rec.agent_opportunity_json if isinstance(rec.agent_opportunity_json, dict) else {}
    if opp:
        assumptions = build_financial_assumptions(opp, existing_assumptions=existing)
    else:
        assumptions = existing or None
    if assumptions is None:
        return None
    return _merge_overrides(assumptions, overrides)


def recompute_recommendation(
    rec: Recommendation,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute assumptions, projections, and ARC Score on a Recommendation row."""
    previous_npv = None
    if isinstance(rec.scenarios_json, dict):
        previous_npv = (rec.scenarios_json.get("npv") or {}).get("expected")

    assumptions = build_recommendation_assumptions(rec, overrides=overrides)
    if assumptions is None:
        rec.financial_evaluation_status = "skipped"
        apply_arc_score(rec)
        return {
            "financial_status": "skipped",
            "previous_npv": previous_npv,
            "new_npv": None,
            "arc_score": rec.arc_score_json,
        }

    projections = compute_projections(assumptions, automation_type=rec.automation_type)
    new_npv = projections["npv"]["expected"]
    rec.assumptions_json = assumptions
    rec.scenarios_json = projections
    rec.estimated_roi = Decimal(str(new_npv))
    rec.financial_evaluation_status = "completed"
    arc_score = apply_arc_score(rec)

    return {
        "financial_status": "completed",
        "previous_npv": previous_npv,
        "new_npv": new_npv,
        "arc_score": arc_score,
        "computed_at": datetime.now(tz=UTC).isoformat(),
    }
