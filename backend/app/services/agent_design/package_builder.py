from __future__ import annotations

from app.services.agent_design.source_compiler import safe_identifier
from app.services.agent_design.validators import validate_design_package


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _text(value: object, fallback: str = "") -> str:
    return str(value or fallback).strip()


def _known_objects(context: dict) -> set[str]:
    return {
        _text(o.get("api_name"))
        for o in _as_list((context.get("salesforce_metadata") or {}).get("objects"))
        if isinstance(o, dict) and _text(o.get("api_name"))
    }


def _best_object_name(raw: str, known_objects: set[str]) -> str:
    candidate = raw.strip()
    if candidate in known_objects:
        return candidate
    for known in sorted(known_objects):
        if known.lower() == candidate.lower():
            return known
    return candidate


def _action_contract_name(topic_name: str, action_name: str, seen: set[str]) -> str:
    base = safe_identifier(action_name or topic_name or "AgentAction", fallback="AgentAction")
    if not base.lower().endswith("action"):
        base = base.removesuffix("Actions")
    name = base
    if name in seen:
        name = safe_identifier(f"{topic_name} {action_name}", fallback="AgentAction")
    i = 2
    original = name
    while name in seen:
        name = f"{original}{i}"
        i += 1
    seen.add(name)
    return name


def build_design_package_from_context(context: dict) -> dict:
    """Build the first reviewable Agent Design Package from recommendation context.

    This is intentionally deterministic for v1. The high-reasoning operation can
    refine the same IR later without changing the compiler boundary.
    """
    rec = context.get("recommendation") or {}
    opportunity = rec.get("agent_opportunity") or {}
    known_objects = _known_objects(context)
    raw_data_requirements = [_text(v) for v in _as_list(opportunity.get("data_requirements")) if _text(v)]
    data_requirements = [_best_object_name(v, known_objects) for v in raw_data_requirements]
    if not data_requirements and known_objects:
        data_requirements = [next(iter(sorted(known_objects)))]

    agent_name = _text(opportunity.get("agent_name"), rec.get("title") or "Generated Agent")
    agent_type = _text(opportunity.get("agent_type"), rec.get("automation_type") or "hybrid")
    topics = []
    action_contracts = []
    seen_action_names: set[str] = set()

    for topic in _as_list(opportunity.get("topics")):
        if not isinstance(topic, dict):
            continue
        topic_name = _text(topic.get("topic_name"), "Agent Topic")
        topic_action_names = []
        for raw_action in _as_list(topic.get("actions_needed")) or ["Review context"]:
            contract_name = _action_contract_name(topic_name, _text(raw_action), seen_action_names)
            target_object = data_requirements[0] if data_requirements else "Record"
            topic_action_names.append(contract_name)
            action_contracts.append(
                {
                    "name": contract_name,
                    "label": _text(raw_action, contract_name),
                    "target_type": "apex",
                    "description": (
                        f"{contract_name} is a draft Apex-backed Agentforce action for "
                        f"{topic_name}. Review and replace TODO logic before deploy."
                    ),
                    "salesforce_objects": [target_object] if target_object != "Record" else [],
                    "inputs": [
                        {
                            "name": "recordId",
                            "type": "Id",
                            "required": True,
                            "description": f"Primary {target_object} record for the action.",
                            "object": target_object if target_object != "Record" else None,
                        }
                    ],
                    "outputs": [
                        {
                            "name": "status",
                            "type": "String",
                            "required": True,
                            "description": "Action result status.",
                        },
                        {
                            "name": "rationale",
                            "type": "String",
                            "required": False,
                            "description": "Human-readable reason for the recommendation.",
                        },
                    ],
                    "permissions": [f"{target_object}:read", f"{target_object}:update"]
                    if target_object != "Record"
                    else [],
                    "error_states": ["MISSING_ACCESS", "RECORD_NOT_FOUND", "REVIEW_REQUIRED"],
                    "human_in_loop": True,
                }
            )
        topics.append(
            {
                "name": topic_name,
                "description": _text(topic.get("description"), "Agent topic generated from Arcflare analysis."),
                "reasoning_type": _text(topic.get("reasoning_type"), "hybrid"),
                "actions": topic_action_names,
                "source_actions_needed": _as_list(topic.get("actions_needed")),
            }
        )

    permission_requirements = [
        {
            "object": obj,
            "operations": ["read", "update"],
            "reason": "Required by generated Agentforce action contracts.",
        }
        for obj in data_requirements
        if obj in known_objects
    ]

    test_scenarios = []
    for replacement in _as_list(opportunity.get("replaces")):
        if not isinstance(replacement, dict):
            continue
        process_name = _text(replacement.get("process_name"), "linked process")
        test_scenarios.append(
            {
                "name": f"Handles {process_name}",
                "given": f"The agent has access to the data needed for {process_name}.",
                "when": "The user or automation invokes the matching topic.",
                "then": "The agent calls the approved action contract and returns a reviewable result.",
                "source_process_id": _text(replacement.get("process_id")),
                "source_step_ids": _as_list(replacement.get("step_ids")),
            }
        )

    package = {
        "schema_version": "agent_design_package_v1",
        "builder_version": "deterministic_package_builder_v1",
        "agent": {
            "name": agent_name,
            "type": agent_type,
            "summary": _text(opportunity.get("description"), rec.get("description") or ""),
            "trigger": _text(opportunity.get("trigger"), "Manual or Flow-triggered invocation"),
        },
        "topics": topics,
        "session_variables": [
            {
                "name": "recordId",
                "type": "Id",
                "description": "Primary Salesforce record id for the active agent turn.",
            }
        ],
        "action_contracts": action_contracts,
        "permission_requirements": permission_requirements,
        "test_scenarios": test_scenarios
        or [
            {
                "name": "Generated action returns reviewable result",
                "given": "A user invokes the generated topic",
                "when": "The Apex-backed action runs",
                "then": "The action returns a safe REVIEW_REQUIRED status",
            }
        ],
        "observability": {
            "events": ["agent_design_package_created", "agent_source_bundle_generated"],
            "trace_keys": ["recommendation_id", "generation_run_id", "action_contract_name"],
        },
        "integration_requirements": [
            {
                "name": _text(item),
                "status": "requires_apex_middleware",
                "reason": "External systems must be mediated by Apex or another Salesforce action target.",
            }
            for item in _as_list(opportunity.get("integration_points"))
            if _text(item)
        ],
        "source_evidence": {
            "recommendation_id": rec.get("id"),
            "linked_process_count": len(context.get("processes") or []),
            "arc_score": rec.get("arc_score") or {},
            "processes": context.get("processes") or [],
        },
        "blockers": [],
    }
    validation = validate_design_package(package, known_salesforce_objects=known_objects)
    package["blockers"] = validation["blockers"]
    package["warnings"] = validation["warnings"]
    return package
