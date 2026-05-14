"""Financial assumption modeling for recommendation projections.

This module deliberately keeps the first model deterministic and explainable.
The LLM proposes candidate opportunities; Arcflare owns the cost model.
"""
from __future__ import annotations

import re
from typing import Any

ASSUMPTION_MODEL_VERSION = "agent_investment_pilot_v1"

ROLE_SALARY: dict[str, int] = {
    "sales_operations": 70_000,
    "sales_representative": 75_000,
    "sales_development_representative": 65_000,
    "account_executive": 110_000,
    "account_manager": 85_000,
    "engineering": 130_000,
    "platform_engineer": 130_000,
    "software_engineer": 125_000,
    "sre": 130_000,
    "customer_support": 55_000,
    "support_agent": 55_000,
    "support_case_manager": 65_000,
    "technical_account_manager": 95_000,
    "finance_operations": 80_000,
    "finance_analyst": 80_000,
    "commission_manager": 85_000,
    "marketing": 90_000,
    "operations": 75_000,
    "operations_coordinator": 70_000,
    "product_manager": 110_000,
    "business_analyst": 85_000,
    "data_analyst": 80_000,
    "system_administrator": 85_000,
    "administrative_user": 55_000,
    "devops": 125_000,
    "architect": 140_000,
    "user": 75_000,
}

_ROLE_SUFFIX_STRIP = [
    "specialist",
    "analyst",
    "coordinator",
    "owner",
    "lead",
    "senior",
    "junior",
    "associate",
    "manager",
]

_NATIVE_SALESFORCE_TERMS = (
    "__c",
    "__cio",
    "__r",
    "apex",
    "approval process",
    "automation",
    "campaignmember",
    "class",
    "component",
    "contact",
    "controller",
    "custom object",
    "data cloud",
    "emailtemplate",
    "feeditem",
    "field",
    "financialforce",
    "flow",
    "fw1__",
    "invocable",
    "lead",
    "lightning",
    "object",
    "opportunity",
    "opportunitylineitem",
    "page",
    "pricebook",
    "process builder",
    "platform event",
    "record",
    "salesforce",
    "task",
    "trigger",
    "validation rule",
    "workflow",
)

_EXTERNAL_TERMS = (
    "calendly",
    "connector",
    "erp",
    "external",
    "hubspot crm",
    "middleware",
    "mulesoft",
    "netsuite",
    "notification system",
    "quickbooks",
    "service bus",
    "slack",
    "stripe",
    "teams",
    "third-party",
    "webhook",
    "workday",
    "zendesk",
)

_EXPLICIT_EXTERNAL_TERMS = (
    "external",
    "integration connector",
    "integration for",
    "middleware",
    "notification channel",
    "notification service",
    "notification system",
    "scheduling integration",
    "service bus",
    "third-party",
    "webhook",
)

_EXTERNAL_API_PREFIXES = (
    "calendly",
    "hubspot",
    "mulesoft",
    "netsuite",
    "quickbooks",
    "slack",
    "stripe",
    "teams",
    "workday",
    "zendesk",
)

_COMPLEXITY_NATIVE_BUILD = {"low": 5_000, "medium": 8_000, "high": 12_000}
_COMPLEXITY_GOVERNANCE = {"low": 1_500, "medium": 3_000, "high": 5_000}
_COMPLEXITY_CHANGE_FACTOR = {"low": 0.15, "medium": 0.20, "high": 0.25}
_COMPLEXITY_ENTERPRISE_MULTIPLIER = {"low": 1.45, "medium": 1.70, "high": 2.00}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_role_salary(raw: str) -> int:
    """Map a freeform LLM role string to the closest salary benchmark."""
    s = re.sub(r"[^a-z0-9]+", "_", raw.lower().strip()).strip("_")
    if s in ROLE_SALARY:
        return ROLE_SALARY[s]

    for key, salary in ROLE_SALARY.items():
        if key in s or s in key:
            return salary

    base = s
    for suffix in _ROLE_SUFFIX_STRIP:
        base = base.replace(f"_{suffix}", "").strip("_")
    if base != s and base in ROLE_SALARY:
        return ROLE_SALARY[base]
    for key, salary in ROLE_SALARY.items():
        if key in base or base in key:
            return salary

    return 75_000


def _is_native_salesforce_touchpoint(value: str) -> bool:
    text = value.lower()
    return any(term in text for term in _NATIVE_SALESFORCE_TERMS)


def _is_external_integration(value: str) -> bool:
    text = value.lower()
    native_hit = _is_native_salesforce_touchpoint(value)
    external_hit = any(term in text for term in _EXTERNAL_TERMS)
    explicit_external = any(term in text for term in _EXPLICIT_EXTERNAL_TERMS)
    api_hit = bool(re.search(r"\bapis?\b", text))
    vendor_api_hit = api_hit and any(vendor in text for vendor in _EXTERNAL_API_PREFIXES)
    salesforce_object_api = native_hit and (
        "__c" in text
        or "__cio" in text
        or "salesforce" in text
        or "data cloud object" in text
        or bool(re.search(r"\b[a-z0-9_ ]+ object apis?\b", text))
    )

    # Salesforce-native records and metadata often contain words like "API" or
    # package/vendor names. Those are implementation touchpoints, not external
    # integration cost drivers, unless the text explicitly names an outside
    # service API/connector.
    if native_hit:
        if vendor_api_hit and not salesforce_object_api:
            return True
        if explicit_external and not salesforce_object_api:
            return True
        return False

    return external_hit or explicit_external or api_hit


def classify_touchpoints(raw_touchpoints: list[Any] | None) -> dict[str, Any]:
    """Split candidate touchpoints into native Salesforce and true integrations."""
    native: list[str] = []
    external: list[str] = []
    unknown: list[str] = []

    for item in raw_touchpoints or []:
        value = str(item).strip()
        if not value:
            continue
        if _is_external_integration(value):
            external.append(value)
        elif _is_native_salesforce_touchpoint(value):
            native.append(value)
        else:
            unknown.append(value)

    return {
        "native_salesforce_touchpoints": native,
        "external_integrations": external,
        "unknown_touchpoints": unknown,
        "native_salesforce_touchpoint_count": len(native),
        "external_integration_count": len(external),
        "unknown_touchpoint_count": len(unknown),
    }


def derive_efficiency_gain(opp_json: dict) -> float:
    """Vary efficiency by agent type and replacement coverage."""
    agent_type = opp_json.get("agent_type", "hybrid")
    replaces = opp_json.get("replaces") or []
    full_count = sum(1 for r in replaces if isinstance(r, dict) and r.get("replacement_type") == "full")
    total = len(replaces) or 1
    full_ratio = full_count / total
    base = {"headless": 0.82, "conversational": 0.42, "hybrid": 0.60}.get(agent_type, 0.55)
    return round(min(base + full_ratio * 0.08, 0.90), 2)


def _has_agentic_reasoning(opp_json: dict) -> bool:
    topics = opp_json.get("topics") or []
    return any(
        isinstance(t, dict) and t.get("reasoning_type") in ("agentic", "hybrid")
        for t in topics
    )


def _investment_components(opp_json: dict, actor_count: int) -> tuple[dict[str, int], dict[str, Any]]:
    complexity = str(opp_json.get("complexity_estimate") or "medium").lower()
    if complexity not in _COMPLEXITY_NATIVE_BUILD:
        complexity = "medium"

    topics = [t for t in (opp_json.get("topics") or []) if isinstance(t, dict)]
    classified = classify_touchpoints(opp_json.get("integration_points") or [])
    native_count = classified["native_salesforce_touchpoint_count"]
    external_count = classified["external_integration_count"]
    unknown_count = classified["unknown_touchpoint_count"]

    native_salesforce_build = (
        _COMPLEXITY_NATIVE_BUILD[complexity]
        + min(native_count, 8) * 500
        + max(len(topics) - 1, 0) * 750
    )
    external_integration = external_count * 4_000 + unknown_count * 1_500
    agentforce_runtime = 3_000 if _has_agentic_reasoning(opp_json) else 1_000
    governance_testing = _COMPLEXITY_GOVERNANCE[complexity] + min(actor_count, 8) * 250

    subtotal = native_salesforce_build + external_integration + agentforce_runtime + governance_testing
    change_management = round(subtotal * _COMPLEXITY_CHANGE_FACTOR[complexity])

    components = {
        "native_salesforce_build": round(native_salesforce_build),
        "external_integration": round(external_integration),
        "agentforce_runtime": round(agentforce_runtime),
        "governance_testing": round(governance_testing),
        "change_management": round(change_management),
    }
    enterprise_hardened = round(
        (subtotal + change_management) * _COMPLEXITY_ENTERPRISE_MULTIPLIER[complexity]
    )
    investment_range = {
        "pilot_mvp": round(subtotal + change_management),
        "expected": round(subtotal + change_management),
        "enterprise_hardened": enterprise_hardened,
    }
    return components, {"classification": classified, "range": investment_range}


def build_financial_assumptions(
    opp_json: dict,
    *,
    existing_assumptions: dict | None = None,
) -> dict | None:
    """Build projection assumptions from an agent opportunity.

    Returns None when there is not enough financial evidence to project value.
    """
    signals = opp_json.get("financial_signals")
    if not isinstance(signals, dict):
        return None
    hours = _safe_float(signals.get("estimated_hours_per_week_saved"))
    if hours <= 0:
        return None

    existing = dict(existing_assumptions or {})
    overrides = existing.get("overrides") if isinstance(existing.get("overrides"), dict) else {}

    role_raw = str(signals.get("primary_role_type") or "operations")
    fte_cost = normalize_role_salary(role_raw)
    actor_count = max(1, _safe_int(signals.get("estimated_actor_count"), 1))
    frequency = str(signals.get("estimated_frequency") or "daily").lower()

    components, meta = _investment_components(opp_json, actor_count)
    expected_investment = meta["range"]["expected"]
    tech_cost = expected_investment - components["change_management"]
    change_factor = components["change_management"] / tech_cost if tech_cost > 0 else 0.0

    topics = opp_json.get("topics") or []
    estimated_actions = max(len(topics) * 3, 3)
    invocations_per_month = {"daily": 22, "weekly": 4, "monthly": 1, "ad-hoc": 8}.get(frequency, 10)
    # Approximate current Agentforce action economics while keeping a versioned
    # assumption; customers can override once actual wallet data is available.
    action_cost = 0.10
    annual_op_cost = (
        estimated_actions * action_cost * invocations_per_month * 12 * actor_count
        if _has_agentic_reasoning(opp_json)
        else 1_200
    )

    return {
        "assumption_model_version": ASSUMPTION_MODEL_VERSION,
        "fte_annual_cost": fte_cost,
        "hours_per_week": hours,
        "frequency": frequency,
        "actor_count": actor_count,
        "role_type": role_raw.lower().strip(),
        "technology_cost": round(tech_cost),
        "change_management_factor": round(change_factor, 4),
        "annual_operational_cost": round(annual_op_cost, 2),
        "adoption_ramp": [0.1, 0.5, 0.85, 0.95, 1.0],
        "productivity_dip": 0.05,
        "efficiency_gain": derive_efficiency_gain(opp_json),
        "hard_savings_pct": 0.25,
        "discount_rate": 0.10,
        "investment_components": components,
        "investment_range": meta["range"],
        "touchpoint_classification": meta["classification"],
        "agentforce_pricing_basis": {
            "unit": "action",
            "estimated_action_cost_usd": action_cost,
            "source": "salesforce_agentforce_flex_credit_public_pricing",
        },
        "source": "auto_estimated",
        "overrides": dict(overrides),
    }
