"""Portfolio classification and Generate Agent readiness gates.

This layer deliberately separates recommendation value from Agentforce suitability.
High ROI can make an item worth doing, but it does not make it an agent.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.services.recommendations.financial_assumptions import classify_touchpoints

AGENT_RUNTIME_TERMS = (
    "ambiguous",
    "ambiguity",
    "classif",
    "context",
    "exception",
    "judgment",
    "judge",
    "next best",
    "priorit",
    "reason",
    "recommend",
    "summar",
    "triage",
    "unstructured",
)

DETERMINISTIC_TERMS = (
    "deterministic",
    "etl",
    "field update",
    "flow",
    "if/then",
    "map payload",
    "mapping",
    "orchestrator",
    "sync",
    "synchronization",
    "webhook",
)

NOTIFICATION_TERMS = (
    "email",
    "notify",
    "notification",
    "send alert",
    "slack",
    "task",
)

ANALYTICS_TERMS = (
    "analytics",
    "dashboard",
    "forecast",
    "insight",
    "metric",
    "report",
)

POLICY_TERMS = (
    "policy",
    "procedure",
    "training",
    "change management",
    "enablement",
)

EXTERNAL_SYSTEM_TERMS = (
    "api",
    "quickbooks",
    "netsuite",
    "stripe",
    "workday",
    "sap",
    "mulesoft",
    "middleware",
    "external",
    "integration",
)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text(*parts: Any) -> str:
    chunks: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, Mapping):
            chunks.extend(str(v) for v in part.values())
        elif isinstance(part, list):
            chunks.extend(str(v) for v in part)
        else:
            chunks.append(str(part))
    return " ".join(chunks).lower()


def _reasoning_types(opportunity: Mapping[str, Any]) -> set[str]:
    return {
        str(t.get("reasoning_type") or "").strip().lower()
        for t in _as_list(opportunity.get("topics"))
        if isinstance(t, Mapping) and t.get("reasoning_type")
    }


def _metadata_manifest(opportunity: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = (
        opportunity.get("metadata_binding_manifest_v1")
        or opportunity.get("metadata_bindings_v1")
        or {}
    )
    return payload if isinstance(payload, Mapping) else {}


def _validated_bindings(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        b
        for b in _as_list(manifest.get("bindings"))
        if isinstance(b, Mapping) and b.get("status") == "validated"
    ]


def _unresolved_binding_count(manifest: Mapping[str, Any]) -> int:
    return len(_as_list(manifest.get("unresolved_bindings"))) + len(
        _as_list(manifest.get("unresolved_external_dependencies"))
    )


def _quality_gate_missing_evidence(manifest: Mapping[str, Any]) -> list[str]:
    gates = manifest.get("quality_gates")
    if not isinstance(gates, Mapping):
        return []
    missing = gates.get("missing_evidence")
    return [str(item) for item in _as_list(missing)]


def _linked_process_ids(
    opportunity: Mapping[str, Any],
    linked_process_ids: Sequence[Any] | None,
) -> list[str]:
    ids = [str(x) for x in (linked_process_ids or []) if x]
    for rep in _as_list(opportunity.get("replaces")):
        if isinstance(rep, Mapping) and rep.get("process_id"):
            ids.append(str(rep["process_id"]))
    return sorted(set(ids))


def _linked_step_ids(
    opportunity: Mapping[str, Any],
    linked_step_ids: Sequence[Any] | None,
) -> list[str]:
    ids = [str(x) for x in (linked_step_ids or []) if x]
    for rep in _as_list(opportunity.get("replaces")):
        if not isinstance(rep, Mapping):
            continue
        ids.extend(str(x) for x in _as_list(rep.get("step_ids")) if x)
    return sorted(set(ids))


def _external_touchpoint_count(opportunity: Mapping[str, Any]) -> int:
    raw = _as_list(opportunity.get("integration_points"))
    classified = classify_touchpoints(raw)
    return int(classified.get("external_integration_count") or 0)


def _contains_any(blob: str, terms: Sequence[str]) -> bool:
    return any(term in blob for term in terms)


def _runtime_reasoning_required(opportunity: Mapping[str, Any]) -> bool:
    reasoning = _reasoning_types(opportunity)
    if "agentic" in reasoning:
        return True
    blob = _text(
        opportunity.get("agent_name"),
        opportunity.get("description"),
        opportunity.get("rationale"),
        opportunity.get("risks"),
        [
            item.get("description", "")
            for item in _as_list(opportunity.get("topics"))
            if isinstance(item, Mapping)
        ],
    )
    if "hybrid" in reasoning and _contains_any(blob, AGENT_RUNTIME_TERMS):
        return True
    return _contains_any(blob, AGENT_RUNTIME_TERMS) and not _contains_any(
        blob, DETERMINISTIC_TERMS
    )


def classify_opportunity(
    opportunity: Mapping[str, Any] | None,
    *,
    linked_process_ids: Sequence[Any] | None = None,
    linked_step_ids: Sequence[Any] | None = None,
    arc_decision: str | None = None,
) -> dict[str, Any]:
    """Classify a recommendation into portfolio and Agent Builder readiness."""
    opp: Mapping[str, Any] = opportunity or {}
    blob = _text(
        opp.get("agent_name"),
        opp.get("description"),
        opp.get("rationale"),
        opp.get("risks"),
        opp.get("integration_points"),
        opp.get("topics"),
    )
    reasoning = _reasoning_types(opp)
    deterministic_only = bool(reasoning) and reasoning <= {"deterministic"}
    external_count = _external_touchpoint_count(opp)
    has_external_language = _contains_any(blob, EXTERNAL_SYSTEM_TERMS)
    notification_only = _contains_any(blob, NOTIFICATION_TERMS) and not _contains_any(
        blob, AGENT_RUNTIME_TERMS
    )
    analytics = _contains_any(blob, ANALYTICS_TERMS)
    policy = _contains_any(blob, POLICY_TERMS)
    requires_reasoning = _runtime_reasoning_required(opp)

    manifest = _metadata_manifest(opp)
    validated = _validated_bindings(manifest)
    unresolved_count = _unresolved_binding_count(manifest)
    missing_evidence = _quality_gate_missing_evidence(manifest)
    process_ids = _linked_process_ids(opp, linked_process_ids)
    step_ids = _linked_step_ids(opp, linked_step_ids)

    blockers: list[str] = []
    if not process_ids:
        blockers.append("missing_validated_process")
    if not step_ids:
        blockers.append("missing_validated_steps")
    if not validated:
        blockers.append("missing_validated_metadata_bindings")
    if unresolved_count:
        blockers.append("unresolved_metadata_dependencies")
    blockers.extend(missing_evidence)
    blockers = sorted(set(blockers))

    if deterministic_only and (external_count or has_external_language):
        candidate_type = "external_integration_candidate"
        automation_path = "external_integration"
        recommended_next_action = "define_integration_contract"
        not_agent_reason = (
            "This is a deterministic integration/sync workflow, so it should be "
            "designed as an integration contract or middleware job rather than an agent."
        )
    elif external_count and not requires_reasoning:
        candidate_type = "external_integration_candidate"
        automation_path = "external_integration"
        recommended_next_action = "define_integration_contract"
        not_agent_reason = (
            "The main work is moving structured data between systems, not runtime reasoning."
        )
    elif deterministic_only or notification_only:
        candidate_type = "flow_candidate"
        automation_path = "salesforce_flow"
        recommended_next_action = "design_flow"
        not_agent_reason = (
            "This is deterministic automation; Flow or Apex is a better fit than Agentforce."
        )
    elif analytics and not requires_reasoning:
        candidate_type = "analytics_candidate"
        automation_path = "analytics"
        recommended_next_action = "design_metric_view"
        not_agent_reason = (
            "The value is analytical visibility, not an agent taking actions at runtime."
        )
    elif policy and not requires_reasoning:
        candidate_type = "human_process_or_policy_fix"
        automation_path = "human_process"
        recommended_next_action = "document_policy_fix"
        not_agent_reason = (
            "The primary gap is process or policy clarity, not software automation."
        )
    elif requires_reasoning:
        candidate_type = "agent_candidate"
        automation_path = "agentforce_agent"
        recommended_next_action = "generate_agent"
        not_agent_reason = ""
    else:
        candidate_type = "needs_evidence"
        automation_path = "needs_evidence"
        recommended_next_action = "collect_evidence"
        not_agent_reason = (
            "Arcflare does not have enough evidence that this needs runtime reasoning."
        )

    if candidate_type == "agent_candidate":
        if blockers:
            agent_readiness_status = "needs_evidence"
            generate_agent_allowed = False
            disabled_reason = (
                "Agent design needs stronger upstream evidence before source generation."
            )
            recommended_next_action = "collect_evidence"
        elif arc_decision in {"blocked", "defer"}:
            agent_readiness_status = "blocked"
            generate_agent_allowed = False
            disabled_reason = "ARC Score is not ready for Agent Builder."
        else:
            agent_readiness_status = "ready"
            generate_agent_allowed = True
            disabled_reason = None
    elif candidate_type == "needs_evidence":
        agent_readiness_status = "needs_evidence"
        generate_agent_allowed = False
        disabled_reason = not_agent_reason
    else:
        agent_readiness_status = "not_agent"
        generate_agent_allowed = False
        disabled_reason = not_agent_reason

    if candidate_type == "agent_candidate":
        portfolio_category = "agent_candidate"
    elif agent_readiness_status == "needs_evidence":
        portfolio_category = "needs_evidence"
    elif candidate_type == "no_build":
        portfolio_category = "no_build"
    else:
        portfolio_category = "automation_integration"

    evidence_bits = [
        f"{len(process_ids)} process link(s)",
        f"{len(step_ids)} step link(s)",
        f"{len(validated)} validated metadata binding(s)",
    ]
    if unresolved_count:
        evidence_bits.append(f"{unresolved_count} unresolved dependency signal(s)")

    if candidate_type == "agent_candidate":
        agent_fit_summary = (
            "Good Agentforce fit: the work includes bounded runtime reasoning and "
            "validated process/metadata evidence."
            if generate_agent_allowed
            else "Potential Agentforce fit, but upstream evidence is incomplete."
        )
    else:
        agent_fit_summary = disabled_reason or "Not an Agentforce candidate."

    return {
        "candidate_type": candidate_type,
        "portfolio_category": portfolio_category,
        "automation_path": automation_path,
        "requires_runtime_reasoning": requires_reasoning,
        "agent_readiness_status": agent_readiness_status,
        "generate_agent_allowed": generate_agent_allowed,
        "generate_agent_disabled_reason": disabled_reason,
        "generate_agent_blockers": blockers,
        "recommended_next_action": recommended_next_action,
        "agent_fit_summary": agent_fit_summary,
        "evidence_summary": "; ".join(evidence_bits),
    }


def build_recommendation_readiness(recommendation: Any) -> dict[str, Any]:
    """Build the readiness envelope for a persisted Recommendation row."""
    opportunity = getattr(recommendation, "agent_opportunity_json", None) or {}
    arc_score = getattr(recommendation, "arc_score_json", None) or {}
    arc_decision = arc_score.get("decision") if isinstance(arc_score, Mapping) else None
    return classify_opportunity(
        opportunity,
        linked_process_ids=getattr(recommendation, "linked_process_ids", None),
        linked_step_ids=getattr(recommendation, "linked_step_ids", None),
        arc_decision=arc_decision,
    )
