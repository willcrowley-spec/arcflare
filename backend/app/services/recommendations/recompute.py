"""Central recomputation boundary for recommendation financials and ARC Score."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.organization import Organization
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


def build_org_assumption_context(
    settings_json: dict[str, Any] | None,
    *,
    business_entity_headcount: int | None = None,
) -> dict[str, Any]:
    settings = settings_json if isinstance(settings_json, dict) else {}
    context = {
        "human_users": settings.get("human_users"),
        "active_users": settings.get("active_users"),
        "system_users": settings.get("system_users"),
        "external_users": settings.get("external_users"),
        "license_summary": settings.get("license_summary"),
    }
    if business_entity_headcount is not None:
        context["business_entity_headcount"] = business_entity_headcount
    return context


async def load_recommendation_assumption_context(
    db: AsyncSession,
    org_id: UUID,
) -> dict[str, Any]:
    org = await db.get(Organization, org_id)
    headcount = await db.scalar(
        select(func.coalesce(func.sum(BusinessEntity.headcount), 0)).where(
            BusinessEntity.org_id == org_id,
            BusinessEntity.is_active.is_(True),
        )
    )
    return build_org_assumption_context(
        org.settings_json if org is not None else {},
        business_entity_headcount=int(headcount or 0),
    )


def build_recommendation_assumptions(
    rec: Recommendation,
    *,
    overrides: dict[str, Any] | None = None,
    org_context: dict[str, Any] | None = None,
) -> dict | None:
    existing = _existing_assumptions(rec)
    opp = rec.agent_opportunity_json if isinstance(rec.agent_opportunity_json, dict) else {}
    if opp:
        assumptions = build_financial_assumptions(
            opp,
            existing_assumptions=existing,
            org_context=org_context,
        )
    else:
        assumptions = existing or None
    if assumptions is None:
        return None
    return _merge_overrides(assumptions, overrides)


def recompute_recommendation(
    rec: Recommendation,
    *,
    overrides: dict[str, Any] | None = None,
    org_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute assumptions, projections, and ARC Score on a Recommendation row."""
    previous_npv = None
    if isinstance(rec.scenarios_json, dict):
        previous_npv = (rec.scenarios_json.get("npv") or {}).get("expected")

    assumptions = build_recommendation_assumptions(
        rec,
        overrides=overrides,
        org_context=org_context,
    )
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
