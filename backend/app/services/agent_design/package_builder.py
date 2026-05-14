from __future__ import annotations

import re

from app.services.agent_design.legacy_binding_adapter import (
    resolve_object_references,
    score_text_against_resolved_object,
)
from app.services.agent_design.source_compiler import safe_identifier
from app.services.agent_design.validators import validate_design_package
from app.services.recommendations.metadata_bindings import validated_object_bindings


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


def _metadata_objects(context: dict) -> list[dict]:
    return [
        {"api_name": _text(o.get("api_name")), "label": _text(o.get("label"))}
        for o in _as_list((context.get("salesforce_metadata") or {}).get("objects"))
        if isinstance(o, dict) and _text(o.get("api_name"))
    ]


def _clean_action_text(value: str) -> str:
    cleaned = str(value or "")
    cleaned = re.sub(r"__c\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"\bc\b(?=\s+(?:record|records|object|objects)\b)", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _action_contract_name(topic_name: str, action_name: str, seen: set[str]) -> str:
    base = safe_identifier(_clean_action_text(action_name or topic_name or "AgentAction"), fallback="AgentAction")
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


def _topic_search_text(topic: dict) -> str:
    actions = " ".join(_text(action) for action in _as_list(topic.get("actions_needed")))
    return " ".join(
        [
            _text(topic.get("topic_name")),
            _text(topic.get("description")),
            actions,
        ]
    )


def _matching_objects_for_text(value: object, mapped_objects: list[dict]) -> list[dict]:
    if not mapped_objects:
        return []
    if len(mapped_objects) == 1:
        return mapped_objects
    search_text = _text(value)
    ranked = sorted(
        ((score_text_against_resolved_object(search_text, obj), obj) for obj in mapped_objects),
        key=lambda pair: pair[0],
        reverse=True,
    )
    direct = [obj for score, obj in ranked if score >= 1.0]
    if direct:
        return direct
    best_score, best = ranked[0]
    return [best] if best_score >= 0.72 else []


def _topic_objects(topic: dict, mapped_objects: list[dict]) -> list[dict]:
    return _matching_objects_for_text(_topic_search_text(topic), mapped_objects)


def _dedupe_objects(objects: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for obj in objects:
        api_name = _text(obj.get("api_name"))
        if api_name and api_name not in deduped:
            deduped[api_name] = obj
    return list(deduped.values())


def _metadata_labels(context: dict) -> dict[str, str]:
    return {
        _text(o.get("api_name")): _text(o.get("label"), o.get("api_name"))
        for o in _as_list((context.get("salesforce_metadata") or {}).get("objects"))
        if isinstance(o, dict) and _text(o.get("api_name"))
    }


def _binding_payload(opportunity: dict) -> dict | None:
    for key in ("metadata_bindings_v1", "metadata_bindings"):
        value = opportunity.get(key)
        if isinstance(value, dict) and value.get("schema_version") == "metadata_bindings_v1":
            return value
    return None


def _object_refs_from_bindings(context: dict, payload: dict) -> list[dict]:
    labels = _metadata_labels(context)
    refs = []
    for binding in validated_object_bindings(payload):
        api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if not api_name:
            continue
        refs.append(
            {
                "api_name": api_name,
                "label": labels.get(api_name, api_name),
                "raw": _text(binding.get("raw_value"), api_name),
                "source": _text(binding.get("source")),
                "status": _text(binding.get("status")),
                "confidence": binding.get("confidence"),
                "evidence_ids": _as_list(binding.get("evidence_ids")),
            }
        )
    return _dedupe_objects(refs)


def _metadata_grounding_from_bindings(context: dict, payload: dict) -> dict:
    labels = _metadata_labels(context)
    mapped = []
    unresolved = []
    warnings = []
    for binding in _as_list(payload.get("bindings")):
        if not isinstance(binding, dict):
            continue
        status = _text(binding.get("status"))
        object_api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if status == "validated" and object_api_name:
            if any(row["api_name"] == object_api_name for row in mapped):
                continue
            mapped.append(
                {
                    "raw": _text(binding.get("raw_value"), object_api_name),
                    "status": "validated",
                    "api_name": object_api_name,
                    "label": labels.get(object_api_name, object_api_name),
                    "confidence": binding.get("confidence", 1.0),
                    "source": _text(binding.get("source")),
                    "evidence_ids": _as_list(binding.get("evidence_ids")),
                }
            )
        elif status:
            unresolved.append(
                {
                    "raw": _text(binding.get("raw_value"), object_api_name or "unknown"),
                    "status": status,
                    "ref_type": _text(binding.get("ref_type"), "object"),
                    "api_name": object_api_name or binding.get("api_name"),
                    "source": _text(binding.get("source")),
                    "reason": _text(binding.get("reason"), "requires_review"),
                    "evidence_ids": _as_list(binding.get("evidence_ids")),
                }
            )

    for binding in _as_list(payload.get("unresolved_bindings")):
        if not isinstance(binding, dict):
            continue
        unresolved.append(
            {
                "raw": _text(binding.get("raw_value"), binding.get("api_name") or "unknown"),
                "status": _text(binding.get("status"), "unresolved"),
                "ref_type": _text(binding.get("ref_type"), "object"),
                "api_name": binding.get("api_name"),
                "object_api_name": binding.get("object_api_name"),
                "field_api_name": binding.get("field_api_name"),
                "source": _text(binding.get("source")),
                "reason": _text(binding.get("reason"), "requires_metadata_mapping"),
                "evidence_ids": _as_list(binding.get("evidence_ids")),
            }
        )

    if unresolved:
        warnings.append("Some metadata bindings need analyst review before source generation.")

    return {
        "binding_model_version": payload.get("binding_model_version") or payload.get("schema_version"),
        "mapped": mapped,
        "unresolved": unresolved,
        "legacy_suggestions": [],
        "legacy_adapter_used": False,
        "warnings": warnings,
        "telemetry": dict(payload.get("telemetry") or {}),
    }


def _legacy_grounding(raw_data_requirements: list[str], context: dict) -> dict:
    legacy = resolve_object_references(raw_data_requirements, _metadata_objects(context))
    warnings = list(_as_list(legacy.get("warnings")))
    if raw_data_requirements:
        warnings.append(
            "Legacy string adapter suggestions are review-only and cannot become source dependencies."
        )
    return {
        "binding_model_version": None,
        "mapped": [],
        "unresolved": _as_list(legacy.get("unresolved")),
        "legacy_suggestions": _as_list(legacy.get("mapped")),
        "legacy_adapter_used": bool(raw_data_requirements),
        "warnings": warnings,
        "telemetry": {
            "bindings_from_process_touchpoints": 0,
            "bindings_from_llm_suggestions": 0,
            "bindings_from_legacy_adapter": len(_as_list(legacy.get("mapped"))),
            "unresolved_binding_count": len(_as_list(legacy.get("unresolved"))),
        },
    }


def build_design_package_from_context(context: dict) -> dict:
    """Build the first reviewable Agent Design Package from recommendation context.

    This is intentionally deterministic for v1. The high-reasoning operation can
    refine the same IR later without changing the compiler boundary.
    """
    rec = context.get("recommendation") or {}
    opportunity = rec.get("agent_opportunity") or {}
    known_objects = _known_objects(context)
    raw_data_requirements = [_text(v) for v in _as_list(opportunity.get("data_requirements")) if _text(v)]
    binding_payload = _binding_payload(opportunity)
    if binding_payload:
        metadata_grounding = _metadata_grounding_from_bindings(context, binding_payload)
        mapped_data_requirements = _object_refs_from_bindings(context, binding_payload)
    else:
        metadata_grounding = _legacy_grounding(raw_data_requirements, context)
        mapped_data_requirements = []

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
        default_refs = _topic_objects(topic, mapped_data_requirements)
        for raw_action in _as_list(topic.get("actions_needed")) or ["Review context"]:
            contract_name = _action_contract_name(topic_name, _text(raw_action), seen_action_names)
            target_refs = _dedupe_objects(
                _matching_objects_for_text(f"{topic_name} {raw_action}", mapped_data_requirements) or default_refs
            )
            target_objects = [_text(ref.get("api_name")) for ref in target_refs if _text(ref.get("api_name"))]
            target_label = ", ".join(_text(ref.get("label"), ref.get("api_name")) for ref in target_refs) or "record"
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
                    "salesforce_objects": target_objects,
                    "inputs": [
                        {
                            "name": "recordId",
                            "type": "Id",
                            "required": True,
                            "description": f"Primary {target_label} record for the action.",
                            "object": target_objects[0] if target_objects else None,
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
                    "permissions": [
                        permission for obj in target_objects for permission in (f"{obj}:read", f"{obj}:update")
                    ],
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
            "object": obj["api_name"],
            "operations": ["read", "update"],
            "reason": "Required by validated metadata bindings for generated Agentforce action contracts.",
        }
        for obj in mapped_data_requirements
        if isinstance(obj, dict) and obj.get("api_name") in known_objects
    ]
    permission_requirements = list({p["object"]: p for p in permission_requirements}.values())

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
        "metadata_grounding": metadata_grounding,
        "source_evidence": {
            "recommendation_id": rec.get("id"),
            "linked_process_count": len(context.get("processes") or []),
            "arc_score": rec.get("arc_score") or {},
            "metadata_grounding": metadata_grounding,
            "processes": context.get("processes") or [],
        },
        "blockers": [],
    }
    validation = validate_design_package(package, known_salesforce_objects=known_objects)
    package["blockers"] = validation["blockers"]
    package["warnings"] = validation["warnings"]
    return package
