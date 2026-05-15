"""Algorithmic ARC Score evaluation for agent recommendations.

ARC means Automation Readiness & Confidence.  The score is deliberately
rules-based for v1: LLM confidence is recorded as a signal, but it does not
decide the final ranking.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from app.models.recommendation import Recommendation
from app.services.recommendations.financial_assumptions import classify_touchpoints
from app.services.recommendations.readiness import classify_opportunity

FEATURE_VERSION = "arc_features_v1"
SCORING_METHOD = "rules_v1"
DIVERGENCE_THRESHOLD = 0.25

WEIGHTS = {
    "value": 0.30,
    "feasibility": 0.25,
    "suitability": 0.20,
    "evidence": 0.15,
    "risk_inverse": 0.10,
}

FREQUENCY_SCORE = {
    "daily": 1.0,
    "weekly": 0.65,
    "monthly": 0.35,
    "ad-hoc": 0.25,
    "adhoc": 0.25,
    "per_transaction": 0.85,
}

COMPLEXITY_SCORE = {
    "low": 0.90,
    "medium": 0.65,
    "high": 0.35,
}

RISK_TERMS = (
    "approval",
    "audit",
    "compliance",
    "exception",
    "fraud",
    "high risk",
    "high-risk",
    "legal",
    "manual review",
    "permission",
    "regulatory",
)

UNSUITABLE_TERMS = (
    "cancellation",
    "do not automate",
    "human must",
    "human review required",
    "retention",
    "relationship",
)


def _clamp01(value: float) -> float:
    if value != value:  # NaN guard
        return 0.0
    return min(1.0, max(0.0, value))


def _round_score(value: float) -> float:
    return round(_clamp01(value), 4)


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _binding_counts(opportunity: Mapping[str, Any]) -> dict[str, int]:
    payload = opportunity.get("metadata_binding_manifest_v1") or opportunity.get("metadata_bindings_v1")
    if not isinstance(payload, Mapping):
        return {
            "has_payload": 0,
            "validated": 0,
            "suggested": 0,
            "unresolved": 0,
            "legacy": 0,
        }
    bindings = [b for b in _as_list(payload.get("bindings")) if isinstance(b, Mapping)]
    advisory = [b for b in _as_list(payload.get("advisory_bindings")) if isinstance(b, Mapping)]
    unresolved = [b for b in _as_list(payload.get("unresolved_bindings")) if isinstance(b, Mapping)]
    external = [
        b
        for b in _as_list(payload.get("unresolved_external_dependencies"))
        if isinstance(b, Mapping)
    ]
    return {
        "has_payload": 1,
        "validated": sum(1 for b in bindings if b.get("status") == "validated"),
        "suggested": sum(1 for b in advisory if b.get("status") == "suggested")
        + sum(1 for b in bindings if b.get("status") == "suggested"),
        "unresolved": len(unresolved) + len(external),
        "legacy": int((payload.get("telemetry") or {}).get("bindings_from_legacy_adapter") or 0),
    }


def _text(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _npv_from_scenarios(scenarios_json: Mapping[str, Any] | None) -> float | None:
    if not scenarios_json:
        return None
    npv = scenarios_json.get("npv")
    if isinstance(npv, Mapping):
        val = npv.get("expected")
        if val is not None:
            return _number(val)
    expected = scenarios_json.get("expected")
    if isinstance(expected, Mapping):
        val = expected.get("npv")
        if val is not None:
            return _number(val)
    return None


def _dimension(score: float, signals: Mapping[str, Any], explanation: str) -> dict:
    return {
        "score": _round_score(score),
        "signals": dict(signals),
        "explanation": explanation,
    }


def _assumption_value(
    assumptions: Mapping[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    if not isinstance(assumptions, Mapping):
        return default
    overrides = assumptions.get("overrides")
    if isinstance(overrides, Mapping) and key in overrides:
        return overrides[key]
    return assumptions.get(key, default)


def _score_value(
    opportunity: Mapping[str, Any],
    scenarios_json: Mapping[str, Any] | None,
    assumptions_json: Mapping[str, Any] | None = None,
) -> tuple[dict, list[str]]:
    signals = opportunity.get("financial_signals")
    gaps: list[str] = []
    if not isinstance(signals, Mapping) or not signals:
        gaps.append("missing_financial_signals")
        signals = {}

    hours = max(
        0.0,
        _number(
            _assumption_value(
                assumptions_json,
                "hours_per_week",
                signals.get("estimated_hours_per_week_saved"),
            )
        ),
    )
    actor_count = max(
        0.0,
        _number(
            _assumption_value(
                assumptions_json,
                "actor_count",
                signals.get("estimated_actor_count"),
            ),
            1.0,
        ),
    )
    frequency = str(
        _assumption_value(assumptions_json, "frequency", signals.get("estimated_frequency"))
        or ""
    ).strip().lower()
    hours_basis = _assumption_value(assumptions_json, "hours_basis")
    npv = _npv_from_scenarios(scenarios_json)

    hours_score = _clamp01(hours / 40.0)
    actor_score = _clamp01(actor_count / 5.0)
    frequency_score = FREQUENCY_SCORE.get(frequency, 0.45 if frequency else 0.30)
    npv_score = 0.50 if npv is None else _clamp01(max(0.0, npv) / 250_000.0)

    score = (
        0.35 * hours_score
        + 0.15 * actor_score
        + 0.20 * frequency_score
        + 0.30 * npv_score
    )
    return (
        _dimension(
            score,
            {
                "hours_per_week_saved": hours,
                "hours_basis": hours_basis,
                "actor_count": actor_count,
                "frequency": frequency or None,
                "expected_npv": npv,
            },
            "Business value from saved effort, frequency, affected actors, and expected NPV.",
        ),
        gaps,
    )


def _score_feasibility(opportunity: Mapping[str, Any]) -> tuple[dict, list[str]]:
    gaps: list[str] = []
    complexity = str(opportunity.get("complexity_estimate") or "medium").strip().lower()
    integrations = _as_list(opportunity.get("integration_points"))
    touchpoints = classify_touchpoints(integrations)
    external_count = int(touchpoints["external_integration_count"])
    unknown_count = int(touchpoints["unknown_touchpoint_count"])
    native_count = int(touchpoints["native_salesforce_touchpoint_count"])
    data_requirements = _as_list(opportunity.get("data_requirements"))
    binding_counts = _binding_counts(opportunity)
    topics = _as_list(opportunity.get("topics"))

    if binding_counts["has_payload"]:
        if binding_counts["validated"] == 0:
            gaps.append("missing_validated_metadata_bindings")
        if binding_counts["unresolved"]:
            gaps.append("unresolved_metadata_bindings")
    elif not data_requirements:
        gaps.append("missing_data_requirements")

    complexity_score = COMPLEXITY_SCORE.get(complexity, 0.55)
    if binding_counts["has_payload"]:
        if binding_counts["validated"]:
            data_score = 0.90
        elif binding_counts["suggested"]:
            data_score = 0.55
        else:
            data_score = 0.30
    else:
        data_score = 0.85 if data_requirements else 0.35
    integration_burden = external_count + unknown_count
    if integration_burden == 0:
        integration_score = 1.0
    elif integration_burden <= 1:
        integration_score = 0.85
    elif integration_burden <= 2:
        integration_score = 0.75
    elif integration_burden <= 4:
        integration_score = 0.45
    else:
        integration_score = 0.25
    if native_count <= 4:
        native_scope_score = 1.0
    elif native_count <= 8:
        native_scope_score = 0.85
    else:
        native_scope_score = 0.65

    topic_count = len(topics)
    if topic_count == 0:
        scope_score = 0.0
    elif topic_count == 1:
        scope_score = 0.65
    elif topic_count <= 6:
        scope_score = 0.85
    else:
        scope_score = 0.50

    score = (
        0.30 * complexity_score
        + 0.25 * data_score
        + 0.25 * integration_score
        + 0.10 * native_scope_score
        + 0.10 * scope_score
    )
    return (
        _dimension(
            score,
            {
                "complexity": complexity,
                "integration_count": len(integrations),
                "external_integration_count": external_count,
                "native_touchpoint_count": native_count,
                "unknown_touchpoint_count": unknown_count,
                "data_requirement_count": len(data_requirements),
                "validated_metadata_binding_count": binding_counts["validated"],
                "suggested_metadata_binding_count": binding_counts["suggested"],
                "unresolved_metadata_binding_count": binding_counts["unresolved"],
                "topic_count": topic_count,
            },
            "Feasibility from complexity, data readiness, true external integrations, and native Salesforce scope.",
        ),
        gaps,
    )


def _score_suitability(opportunity: Mapping[str, Any]) -> tuple[dict, list[str]]:
    gaps: list[str] = []
    topics = _as_list(opportunity.get("topics"))
    replaces = _as_list(opportunity.get("replaces"))
    blob = _text(
        opportunity.get("description"),
        opportunity.get("rationale"),
        opportunity.get("risks"),
    )

    risk_hits = [term for term in RISK_TERMS if term in blob]
    unsuitable_hits = [term for term in UNSUITABLE_TERMS if term in blob]

    reasoning_types = {
        str(t.get("reasoning_type") or "").strip().lower()
        for t in topics
        if isinstance(t, Mapping)
    }
    deterministic_only = bool(reasoning_types) and reasoning_types <= {"deterministic"}
    full_replacement_count = sum(
        1
        for item in replaces
        if isinstance(item, Mapping) and item.get("replacement_type") == "full"
    )

    score = 0.86
    score -= min(0.35, 0.07 * len(risk_hits))
    score -= min(0.45, 0.15 * len(unsuitable_hits))
    if deterministic_only:
        score = min(score - 0.25, 0.45)
        gaps.append("flow_may_be_better_than_agent")
    if full_replacement_count and risk_hits:
        score -= 0.10

    return (
        _dimension(
            score,
            {
                "risk_terms": risk_hits,
                "unsuitability_terms": unsuitable_hits,
                "reasoning_types": sorted(reasoning_types),
                "full_replacement_count": full_replacement_count,
            },
            "Suitability from automation fit, judgment/control language, and replacement shape.",
        ),
        gaps,
    )


def _score_evidence(
    opportunity: Mapping[str, Any],
    linked_process_ids: Sequence[Any],
    linked_step_ids: Sequence[Any],
) -> tuple[dict, list[str], list[str]]:
    gaps: list[str] = []
    blockers: list[str] = []
    replaces = _as_list(opportunity.get("replaces"))
    signals = opportunity.get("financial_signals")
    topics = _as_list(opportunity.get("topics"))
    llm_confidence = _clamp01(_number(opportunity.get("confidence")))

    process_ids = [str(x) for x in linked_process_ids if x]
    step_ids = [str(x) for x in linked_step_ids if x]
    replace_process_ids = [
        str(r.get("process_id"))
        for r in replaces
        if isinstance(r, Mapping) and r.get("process_id")
    ]
    replace_step_ids = [
        str(sid)
        for r in replaces
        if isinstance(r, Mapping)
        for sid in _as_list(r.get("step_ids"))
        if sid
    ]

    has_process = bool(process_ids or replace_process_ids)
    has_steps = bool(step_ids or replace_step_ids)
    has_financials = isinstance(signals, Mapping) and bool(signals)

    if not has_process:
        gaps.append("missing_linked_process")
        blockers.append("missing_linked_process")
    if not has_steps:
        gaps.append("missing_linked_steps")
    if not has_financials:
        gaps.append("missing_financial_signals")
    if not topics:
        gaps.append("missing_topics")
        blockers.append("missing_topics")

    score = (
        (0.30 if has_process else 0.0)
        + (0.25 if has_steps else 0.0)
        + (0.20 if replace_process_ids else 0.0)
        + (0.15 if has_financials else 0.0)
        + (0.03 * llm_confidence)
    )
    return (
        _dimension(
            score,
            {
                "linked_process_count": len(process_ids),
                "linked_step_count": len(step_ids),
                "replace_process_count": len(replace_process_ids),
                "replace_step_count": len(replace_step_ids),
                "has_financial_signals": has_financials,
                "llm_confidence": llm_confidence,
                "llm_confidence_weight": 0.03,
            },
            "Evidence quality from resolved processes, steps, replacement mapping, and financial signals.",
        ),
        gaps,
        blockers,
    )


def _score_risk_inverse(opportunity: Mapping[str, Any]) -> tuple[dict, list[str]]:
    gaps: list[str] = []
    complexity = str(opportunity.get("complexity_estimate") or "medium").strip().lower()
    integrations = _as_list(opportunity.get("integration_points"))
    touchpoints = classify_touchpoints(integrations)
    external_count = int(touchpoints["external_integration_count"])
    unknown_count = int(touchpoints["unknown_touchpoint_count"])
    native_count = int(touchpoints["native_salesforce_touchpoint_count"])
    data_requirements = _as_list(opportunity.get("data_requirements"))
    binding_counts = _binding_counts(opportunity)
    blob = _text(opportunity.get("risks"), opportunity.get("description"))
    risk_hits = [term for term in RISK_TERMS if term in blob]
    unsuitable_hits = [term for term in UNSUITABLE_TERMS if term in blob]

    score = 0.92
    if complexity == "medium":
        score -= 0.10
    elif complexity == "high":
        score -= 0.25
    score -= min(0.22, 0.07 * external_count)
    score -= min(0.12, 0.04 * unknown_count)
    score -= min(0.08, 0.01 * max(native_count - 4, 0))
    score -= min(0.30, 0.06 * len(risk_hits))
    score -= min(0.35, 0.12 * len(unsuitable_hits))
    if binding_counts["has_payload"]:
        if binding_counts["validated"] == 0:
            score -= 0.12
            gaps.append("missing_validated_metadata_bindings")
        if binding_counts["unresolved"]:
            score -= min(0.16, 0.04 * binding_counts["unresolved"])
            gaps.append("unresolved_metadata_bindings")
    elif not data_requirements:
        score -= 0.10
        gaps.append("missing_data_requirements")

    return (
        _dimension(
            score,
            {
                "complexity": complexity,
                "integration_count": len(integrations),
                "external_integration_count": external_count,
                "native_touchpoint_count": native_count,
                "unknown_touchpoint_count": unknown_count,
                "validated_metadata_binding_count": binding_counts["validated"],
                "unresolved_metadata_binding_count": binding_counts["unresolved"],
                "risk_terms": risk_hits,
                "unsuitability_terms": unsuitable_hits,
            },
            "Inverse risk score: higher means fewer control, external integration, and complexity concerns.",
        ),
        gaps,
    )


def _decision(
    score: float,
    gaps: Sequence[str],
    blockers: Sequence[str],
    dimensions: Mapping[str, Mapping[str, Any]],
) -> str:
    if blockers:
        return "blocked"
    if (
        _number(dimensions["suitability"].get("score")) < 0.55
        or _number(dimensions["risk_inverse"].get("score")) < 0.55
    ):
        return "defer"
    severe_gaps = {
        "missing_financial_signals",
        "missing_linked_steps",
        "missing_data_requirements",
        "missing_validated_metadata_bindings",
        "unresolved_metadata_bindings",
    }
    if score >= 0.75 and not severe_gaps.intersection(gaps):
        return "ready"
    if score >= 0.50:
        return "review"
    return "defer"


def compute_arc_score(
    opportunity: Mapping[str, Any] | None,
    *,
    linked_process_ids: Sequence[Any] | None = None,
    linked_step_ids: Sequence[Any] | None = None,
    scenarios_json: Mapping[str, Any] | None = None,
    assumptions_json: Mapping[str, Any] | None = None,
) -> dict:
    """Compute the ARC Score payload for a recommendation opportunity."""
    opp: Mapping[str, Any] = opportunity or {}
    linked_process_ids = linked_process_ids or []
    linked_step_ids = linked_step_ids or []

    value, value_gaps = _score_value(opp, scenarios_json, assumptions_json)
    feasibility, feasibility_gaps = _score_feasibility(opp)
    suitability, suitability_gaps = _score_suitability(opp)
    evidence, evidence_gaps, blockers = _score_evidence(opp, linked_process_ids, linked_step_ids)
    risk_inverse, risk_gaps = _score_risk_inverse(opp)

    dimensions = {
        "value": value,
        "feasibility": feasibility,
        "suitability": suitability,
        "evidence": evidence,
        "risk_inverse": risk_inverse,
    }
    score = sum(WEIGHTS[name] * dimensions[name]["score"] for name in WEIGHTS)

    all_gaps = sorted(
        set(value_gaps + feasibility_gaps + suitability_gaps + evidence_gaps + risk_gaps)
    )
    all_blockers = sorted(set(blockers))
    decision = _decision(score, all_gaps, all_blockers, dimensions)
    agent_suitability = classify_opportunity(
        opp,
        linked_process_ids=linked_process_ids,
        linked_step_ids=linked_step_ids,
        arc_decision=decision,
    )
    llm_confidence = _clamp01(_number(opp.get("confidence")))
    rounded = _round_score(score)

    return {
        "label": "ARC Score",
        "expanded_name": "Automation Readiness & Confidence",
        "score": rounded,
        "score_pct": round(rounded * 100),
        "decision": decision,
        "decision_band": decision,
        "agent_suitability": agent_suitability,
        "feature_version": FEATURE_VERSION,
        "scoring_method": SCORING_METHOD,
        "model_version": None,
        "weights": dict(WEIGHTS),
        "dimensions": dimensions,
        "evidence_gaps": all_gaps,
        "blockers": all_blockers,
        "llm_confidence": llm_confidence,
        "divergence": abs(rounded - llm_confidence),
        "computed_at": datetime.now(tz=UTC).isoformat(),
    }


def apply_arc_score(recommendation: Recommendation) -> dict:
    """Compute ARC Score and write compatibility fields onto a Recommendation."""
    payload = compute_arc_score(
        recommendation.agent_opportunity_json or {},
        linked_process_ids=recommendation.linked_process_ids or [],
        linked_step_ids=recommendation.linked_step_ids or [],
        scenarios_json=recommendation.scenarios_json or {},
        assumptions_json=recommendation.assumptions_json or {},
    )
    llm_confidence = payload["llm_confidence"]
    score = payload["score"]

    recommendation.arc_score_json = payload
    recommendation.base_score = score
    recommendation.llm_score = llm_confidence
    recommendation.composite_score = score
    recommendation.score_divergence_flag = abs(score - llm_confidence) >= DIVERGENCE_THRESHOLD
    return payload
