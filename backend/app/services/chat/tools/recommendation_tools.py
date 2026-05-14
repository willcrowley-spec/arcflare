"""LLM tools for recommendation-anchored chat (financial assumption enrichment)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation import Recommendation
from app.services.recommendations.recompute import recompute_recommendation

logger = logging.getLogger(__name__)

RECOMMENDATION_TOOLS: list[dict] = [
    {
        "name": "get_recommendation_details",
        "description": (
            "Loads full read-only details for a single automation recommendation: narrative, "
            "scoring, assumptions, scenario projections, and hard vs soft savings split. "
            "Use when the user asks what the recommendation contains or needs a refresher on numbers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the Recommendation in the current organization.",
                },
            },
            "required": ["recommendation_id"],
        },
        "auto_execute": True,
        "risk_level": "none",
    },
    {
        "name": "get_scoring_breakdown",
        "description": (
            "Returns quantitative ARC Score details for a recommendation: dimensions, evidence gaps, "
            "base_score, llm_score, composite_score, and divergence flag. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the Recommendation in the current organization.",
                },
            },
            "required": ["recommendation_id"],
        },
        "auto_execute": True,
        "risk_level": "none",
    },
    {
        "name": "update_assumption",
        "description": (
            "Merges key/value pairs into assumptions_json.overrides, recomputes financial projections, "
            "updates stored scenarios and estimated ROI, and appends an enrichment log entry. "
            "Requires user confirmation in the UI before execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the Recommendation to update.",
                },
                "overrides": {
                    "type": "object",
                    "description": "Assumption keys and values to merge into assumptions_json.overrides.",
                    "additionalProperties": True,
                },
            },
            "required": ["recommendation_id", "overrides"],
        },
        "auto_execute": False,
        "risk_level": "medium",
    },
]


def _hard_soft_totals(scenarios_json: dict | None) -> dict[str, Any]:
    exp = (scenarios_json or {}).get("expected") or {}
    hard = exp.get("hard_savings") or []
    soft = exp.get("soft_savings") or []
    return {
        "hard_savings_total_5y": sum(hard) if isinstance(hard, list) else None,
        "soft_savings_total_5y": sum(soft) if isinstance(soft, list) else None,
    }


def _assumption_lineage(assumptions: dict) -> dict[str, Any]:
    overrides = assumptions.get("overrides") if isinstance(assumptions.get("overrides"), dict) else {}
    skip = frozenset({"overrides", "source"})
    base_keys = [k for k in assumptions if k not in skip]
    overridden_keys = sorted(overrides.keys()) if overrides else []
    auto_estimated_keys = sorted(k for k in base_keys if k not in overrides)
    return {
        "assumption_source": assumptions.get("source"),
        "overridden_keys": overridden_keys,
        "auto_estimated_keys": auto_estimated_keys,
    }


async def _load_recommendation(
    recommendation_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> Recommendation | None:
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None or rec.org_id != org_id:
        return None
    return rec


async def handle_get_recommendation_details(
    args: dict,
    db: AsyncSession,
    *,
    org_id: UUID,
    **kwargs: Any,
) -> dict:
    _ = kwargs
    raw = args.get("recommendation_id")
    try:
        rid = UUID(str(raw)) if raw else None
    except (ValueError, TypeError):
        rid = None
    if rid is None:
        return {"ok": False, "error": "recommendation_id is required and must be a UUID"}

    rec = await _load_recommendation(rid, org_id, db)
    if rec is None:
        return {"ok": False, "error": "Recommendation not found"}

    assumptions = dict(rec.assumptions_json) if rec.assumptions_json else {}
    scenarios = dict(rec.scenarios_json) if rec.scenarios_json else {}
    analysis = list(rec.analysis_inputs_json) if rec.analysis_inputs_json else []
    split = _hard_soft_totals(scenarios)
    hard_pct = assumptions.get("hard_savings_pct")
    if isinstance(hard_pct, (int, float)):
        split["hard_savings_pct_assumption"] = hard_pct
        split["soft_savings_pct_assumption"] = 1.0 - float(hard_pct)

    return {
        "ok": True,
        "id": str(rec.id),
        "title": rec.title,
        "narrative": rec.description,
        "scoring": {
            "base_score": rec.base_score,
            "llm_score": rec.llm_score,
            "composite_score": rec.composite_score,
            "score_divergence_flag": rec.score_divergence_flag,
            "llm_rationale": rec.llm_rationale,
            "arc_score_json": dict(rec.arc_score_json) if rec.arc_score_json else {},
        },
        "assumptions": assumptions,
        "scenarios": scenarios,
        "hard_soft_split": split,
        "automation_type": rec.automation_type,
        "recommendation_type": rec.recommendation_type,
        "linked_process_ids": list(rec.linked_process_ids or []),
        "analysis_inputs": analysis,
        "enrichment_log_tail": (list(rec.enrichment_log or [])[-5:]),
        **_assumption_lineage(assumptions),
    }


async def handle_get_scoring_breakdown(
    args: dict,
    db: AsyncSession,
    *,
    org_id: UUID,
    **kwargs: Any,
) -> dict:
    _ = kwargs
    raw = args.get("recommendation_id")
    try:
        rid = UUID(str(raw)) if raw else None
    except (ValueError, TypeError):
        rid = None
    if rid is None:
        return {"ok": False, "error": "recommendation_id is required and must be a UUID"}

    rec = await _load_recommendation(rid, org_id, db)
    if rec is None:
        return {"ok": False, "error": "Recommendation not found"}

    return {
        "ok": True,
        "recommendation_id": str(rec.id),
        "base_score": rec.base_score,
        "llm_score": rec.llm_score,
        "composite_score": rec.composite_score,
        "score_divergence_flag": rec.score_divergence_flag,
        "arc_score_json": dict(rec.arc_score_json) if rec.arc_score_json else {},
        "signal_breakdown": (rec.arc_score_json or {}).get("dimensions", {}),
    }


async def execute_update_assumption(
    payload: dict,
    db: AsyncSession,
    org_id: UUID,
) -> dict:
    """Persist assumption overrides and refreshed projections (chat action / confirmed tool)."""
    raw = payload.get("recommendation_id")
    try:
        rid = UUID(str(raw)) if raw else None
    except (ValueError, TypeError):
        rid = None
    if rid is None:
        raise ValueError("recommendation_id is required and must be a UUID")

    overrides_in = payload.get("overrides")
    if not isinstance(overrides_in, dict) or not overrides_in:
        raise ValueError("overrides must be a non-empty object")

    rec = await _load_recommendation(rid, org_id, db)
    if rec is None:
        raise ValueError("Recommendation not found")

    previous_roi = rec.estimated_roi
    prev_npv = None
    if isinstance(rec.scenarios_json, dict):
        prev_npv = (rec.scenarios_json.get("npv") or {}).get("expected")

    result = recompute_recommendation(rec, overrides=overrides_in)
    new_npv = result["new_npv"]
    projections = rec.scenarios_json or {}

    log = list(rec.enrichment_log or [])
    log.append(
        {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "source": "chat",
            "changes": dict(overrides_in),
            "roi_impact": {
                "before": float(previous_roi) if previous_roi is not None else prev_npv,
                "after": float(new_npv) if new_npv is not None else None,
            },
        },
    )
    rec.enrichment_log = log

    await db.commit()
    await db.refresh(rec)

    logger.info(
        "chat_update_assumption org_id=%s recommendation_id=%s keys=%s",
        org_id,
        rid,
        list(overrides_in.keys()),
    )

    delta = None
    if new_npv is not None and prev_npv is not None:
        delta = float(new_npv) - float(prev_npv)
    elif new_npv is not None and previous_roi is not None:
        delta = float(new_npv) - float(previous_roi)

    return {
        "ok": True,
        "recommendation_id": str(rec.id),
        "npv_by_scenario": projections.get("npv"),
        "npv_expected": new_npv,
        "npv_impact_expected": delta,
        "payback_month": projections.get("payback_month"),
        "estimated_roi": float(rec.estimated_roi) if rec.estimated_roi is not None else None,
        "arc_score": rec.arc_score_json,
    }
