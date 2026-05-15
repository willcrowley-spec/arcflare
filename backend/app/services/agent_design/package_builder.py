from __future__ import annotations

import re

from app.services.agent_design.legacy_binding_adapter import resolve_object_references
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


def _metadata_objects(context: dict) -> list[dict]:
    return [
        {"api_name": _text(o.get("api_name")), "label": _text(o.get("label"))}
        for o in _as_list((context.get("salesforce_metadata") or {}).get("objects"))
        if isinstance(o, dict) and _text(o.get("api_name"))
    ]


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
    for key in ("metadata_binding_manifest_v1", "metadata_bindings_v1", "metadata_bindings"):
        value = opportunity.get(key)
        if isinstance(value, dict) and value.get("schema_version") in {
            "metadata_binding_manifest_v1",
            "metadata_bindings_v1",
        }:
            return value
    return None


def _permission_operations(operation: object) -> list[str]:
    raw = _text(operation).lower()
    ops: set[str] = set()
    if raw in {"create", "insert"}:
        ops.update({"read", "create"})
    elif raw in {"write", "update", "edit", "upsert"}:
        ops.update({"read", "update"})
    elif raw == "delete":
        ops.update({"read", "delete"})
    else:
        ops.add("read")
    order = ["read", "create", "update", "delete"]
    return [op for op in order if op in ops]


def _merge_operations(existing: list[str] | None, incoming: list[str]) -> list[str]:
    merged = set(existing or []) | set(incoming)
    order = ["read", "create", "update", "delete"]
    return [op for op in order if op in merged]


def _object_refs_from_bindings(context: dict, payload: dict) -> list[dict]:
    labels = _metadata_labels(context)
    refs_by_object: dict[str, dict] = {}
    for binding in _as_list(payload.get("bindings")):
        if not isinstance(binding, dict):
            continue
        if _text(binding.get("status")) != "validated":
            continue
        if _text(binding.get("ref_type")) not in {"object", "field"}:
            continue
        api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if not api_name:
            continue
        current = refs_by_object.get(api_name)
        operations = _permission_operations(binding.get("operation"))
        if current:
            current["operations"] = _merge_operations(current.get("operations"), operations)
            current["evidence_ids"] = sorted(
                set(_as_list(current.get("evidence_ids"))) | set(_as_list(binding.get("evidence_ids")))
            )
            continue
        refs_by_object[api_name] = {
                "api_name": api_name,
                "label": labels.get(api_name, api_name),
                "raw": _text(binding.get("raw_value"), api_name),
                "source": _text(binding.get("source")),
                "status": _text(binding.get("status")),
                "confidence": binding.get("confidence"),
                "evidence_ids": _as_list(binding.get("evidence_ids")),
                "operations": operations,
            }
    return list(refs_by_object.values())


def _validated_bindings(payload: dict | None) -> list[dict]:
    bindings = []
    for binding in _as_list((payload or {}).get("bindings")):
        if not isinstance(binding, dict):
            continue
        if _text(binding.get("status")) != "validated":
            continue
        bindings.append(binding)
    return bindings


def _field_bindings(bindings: list[dict]) -> list[dict]:
    return [
        binding
        for binding in bindings
        if _text(binding.get("ref_type")) == "field"
        and _text(binding.get("object_api_name"))
        and _text(binding.get("field_api_name"))
    ]


def _binding_permission(binding: dict) -> list[str]:
    return _permission_operations(binding.get("operation"))


def _binding_operation_row(binding: dict) -> dict:
    return {
        "ref_type": _text(binding.get("ref_type")),
        "object_api_name": _text(binding.get("object_api_name") or binding.get("api_name")) or None,
        "field_api_name": _text(binding.get("field_api_name")) or None,
        "operation": _text(binding.get("operation"), "read"),
        "source": _text(binding.get("source")),
        "evidence_ids": _as_list(binding.get("evidence_ids")),
    }


def _object_names_from_bindings(bindings: list[dict], mapped_refs: list[dict]) -> list[str]:
    names = []
    for binding in bindings:
        name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if name and name not in names:
            names.append(name)
    for ref in mapped_refs:
        name = _text(ref.get("api_name"))
        if name and name not in names:
            names.append(name)
    return names


def _primary_object(mapped_refs: list[dict], bindings: list[dict]) -> str:
    for ref in mapped_refs:
        api_name = _text(ref.get("api_name"))
        if api_name:
            return api_name
    for binding in bindings:
        api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if api_name:
            return api_name
    return "Record"


def _field_refs_from_text(value: str) -> list[tuple[str, str]]:
    refs = []
    for obj, field in re.findall(
        r"\b([A-Z][A-Za-z0-9_]*(?:__c)?)\.([A-Za-z][A-Za-z0-9_]*(?:__c)?)\b",
        value or "",
    ):
        refs.append((_text(obj), _text(field)))
    return refs


def _missing_field_evidence(
    raw_topics: list[dict],
    field_bindings: list[dict],
) -> list[str]:
    validated = {
        (_text(binding.get("object_api_name")).lower(), _text(binding.get("field_api_name")).lower())
        for binding in field_bindings
    }
    missing = []
    for topic in raw_topics:
        for action_text in _as_list(topic.get("actions_needed")):
            for obj, field in _field_refs_from_text(_text(action_text)):
                if (obj.lower(), field.lower()) not in validated:
                    missing.append(f"{obj}.{field}")
    return sorted(dict.fromkeys(missing))


def _domain_stem(agent_name: str, raw_topics: list[dict], primary_object: str) -> str:
    text_blob = " ".join(
        [
            agent_name,
            *[
                " ".join(
                    [
                        _text(topic.get("topic_name")),
                        _text(topic.get("description")),
                        " ".join(_text(a) for a in _as_list(topic.get("actions_needed"))),
                    ]
                )
                for topic in raw_topics
                if isinstance(topic, dict)
            ],
        ]
    ).lower()
    object_name = safe_identifier(primary_object, fallback="Record").removesuffix("C")
    if "triage" in text_blob:
        return f"{object_name}Triage"
    if "handoff" in text_blob:
        return f"{object_name}Handoff"
    if "onboarding" in text_blob:
        return f"{object_name}Onboarding"
    if "classification" in text_blob or "classify" in text_blob:
        return f"{object_name}Classification"
    return object_name


def _var_from_field(field_api_name: str) -> str:
    cleaned = re.sub(r"__c$", "", _text(field_api_name), flags=re.IGNORECASE)
    return safe_identifier(cleaned, fallback="value")[:1].lower() + safe_identifier(cleaned, fallback="value")[1:]


def _contract_permissions(target_objects: list[str], bindings: list[dict], fallback: str = "read") -> list[str]:
    permissions: list[str] = []
    for binding in bindings:
        object_api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if not object_api_name:
            continue
        for op in _binding_permission(binding):
            permission = f"{object_api_name}:{op}"
            if permission not in permissions:
                permissions.append(permission)
    if not permissions:
        for object_api_name in target_objects[:1]:
            for op in _permission_operations(fallback):
                permissions.append(f"{object_api_name}:{op}")
    return permissions


def _source_processes(opportunity: dict) -> list[dict]:
    processes = []
    for replacement in _as_list(opportunity.get("replaces")):
        if not isinstance(replacement, dict):
            continue
        process_id = _text(replacement.get("process_id"))
        if not process_id:
            continue
        processes.append(
            {
                "process_id": process_id,
                "process_name": _text(replacement.get("process_name")),
                "step_ids": _as_list(replacement.get("step_ids")),
                "replacement_type": _text(replacement.get("replacement_type"), "partial"),
            }
        )
    return processes


def _action_contract(
    *,
    name: str,
    common_name: str,
    purpose: str,
    capability_type: str,
    target_objects: list[str],
    bindings: list[dict],
    inputs: list[dict],
    outputs: list[dict],
    source_topics: list[str],
    source_processes: list[dict],
    fallback_operation: str = "read",
) -> dict:
    operations = [_binding_operation_row(binding) for binding in bindings]
    return {
        "name": name,
        "common_name": common_name,
        "label": common_name,
        "purpose": purpose,
        "capability_type": capability_type,
        "target_type": "apex",
        "target_name": f"{name}Action",
        "description": purpose,
        "implementation_status": "scaffold",
        "source_group_id": f"action:{name}",
        "salesforce_objects": target_objects,
        "validated_bindings": bindings,
        "operations": operations,
        "source_topics": source_topics,
        "source_processes": source_processes,
        "inputs": inputs,
        "outputs": outputs,
        "permissions": _contract_permissions(target_objects, bindings, fallback_operation),
        "error_states": ["MISSING_ACCESS", "RECORD_NOT_FOUND", "REVIEW_REQUIRED"],
        "human_in_loop": True,
    }


def _planned_action_contracts(
    *,
    opportunity: dict,
    agent_name: str,
    raw_topics: list[dict],
    mapped_refs: list[dict],
    binding_payload: dict | None,
) -> tuple[list[dict], list[dict], list[str]]:
    validated = _validated_bindings(binding_payload)
    field_bindings = _field_bindings(validated)
    target_objects = _object_names_from_bindings(validated, mapped_refs)
    primary_object = _primary_object(mapped_refs, validated)
    object_label = primary_object.removesuffix("__c")
    stem = _domain_stem(agent_name, raw_topics, primary_object)
    source_process_rows = _source_processes(opportunity)
    all_topic_names = [_text(topic.get("topic_name"), "Agent Topic") for topic in raw_topics]
    blockers = [
        f"field_evidence_missing:{field_ref}"
        for field_ref in _missing_field_evidence(raw_topics, field_bindings)
    ]

    read_bindings = [
        binding
        for binding in field_bindings
        if not set(_binding_permission(binding)).intersection({"create", "update", "delete"})
    ]
    write_bindings = [
        binding
        for binding in field_bindings
        if set(_binding_permission(binding)).intersection({"create", "update", "delete"})
    ]
    object_bindings = [binding for binding in validated if _text(binding.get("ref_type")) == "object"]
    if not read_bindings and target_objects:
        read_bindings = object_bindings[:1] or validated[:1]

    action_text_blob = " ".join(
        _text(action)
        for topic in raw_topics
        for action in _as_list(topic.get("actions_needed"))
    ).lower()

    action_contracts: list[dict] = []
    if target_objects or raw_topics:
        action_contracts.append(
            _action_contract(
                name=f"Load{stem}Context",
                common_name=f"Load {object_label} context",
                purpose=(
                    f"Loads the Salesforce context needed for {agent_name}. "
                    "This replaces separate field-read micro-actions with one reviewable context contract."
                ),
                capability_type="read_context",
                target_objects=target_objects,
                bindings=read_bindings or validated[:1],
                inputs=[
                    {
                        "name": f"{object_label[:1].lower()}{object_label[1:]}Id",
                        "type": "Id",
                        "required": True,
                        "description": f"Primary {object_label} record Id.",
                        "object": primary_object if target_objects else None,
                    }
                ],
                outputs=[
                    {
                        "name": "contextJson",
                        "type": "String",
                        "required": True,
                        "description": "Serialized context available to the agent topic.",
                    },
                    {
                        "name": "status",
                        "type": "String",
                        "required": True,
                        "description": "Context load status.",
                    },
                ],
                source_topics=all_topic_names,
                source_processes=source_process_rows,
                fallback_operation="read",
            )
        )

    if any(token in action_text_blob for token in ("classif", "nlp", "priorit", "compute", "business rules")):
        action_contracts.append(
            _action_contract(
                name=f"Classify{safe_identifier(primary_object, fallback='Record')}",
                common_name=f"Classify {object_label}",
                purpose=(
                    f"Evaluates {object_label} context and returns a bounded classification, priority, "
                    "or decision recommendation for review."
                ),
                capability_type="reasoning",
                target_objects=target_objects,
                bindings=read_bindings or validated[:1],
                inputs=[
                    {
                        "name": "contextJson",
                        "type": "String",
                        "required": True,
                        "description": "Context produced by the context-loading action.",
                    }
                ],
                outputs=[
                    {
                        "name": "classification",
                        "type": "String",
                        "required": False,
                        "description": "Recommended classification or category.",
                    },
                    {
                        "name": "priority",
                        "type": "String",
                        "required": False,
                        "description": "Recommended priority or urgency.",
                    },
                    {
                        "name": "confidence",
                        "type": "Decimal",
                        "required": False,
                        "description": "Confidence from 0 to 1.",
                    },
                    {
                        "name": "rationale",
                        "type": "String",
                        "required": True,
                        "description": "Decision rationale for audit and review.",
                    },
                ],
                source_topics=[
                    _text(topic.get("topic_name"), "Agent Topic")
                    for topic in raw_topics
                    if any(
                        token in " ".join(_text(a) for a in _as_list(topic.get("actions_needed"))).lower()
                        for token in ("classif", "nlp", "priorit", "compute", "business rules")
                    )
                ]
                or all_topic_names,
                source_processes=source_process_rows,
                fallback_operation="read",
            )
        )

    if write_bindings:
        field_inputs = [
            {
                "name": _var_from_field(_text(binding.get("field_api_name"))),
                "type": "String",
                "required": False,
                "description": f"Proposed value for {binding.get('object_api_name')}.{binding.get('field_api_name')}.",
                "object": binding.get("object_api_name"),
                "field": binding.get("field_api_name"),
            }
            for binding in write_bindings
        ]
        action_contracts.append(
            _action_contract(
                name=f"Apply{stem}Decision",
                common_name=f"Apply {object_label} decision",
                purpose=(
                    f"Applies the approved {agent_name} decision in one transaction boundary instead of "
                    "separate field-update actions."
                ),
                capability_type="writeback",
                target_objects=target_objects,
                bindings=write_bindings,
                inputs=[
                    {
                        "name": f"{object_label[:1].lower()}{object_label[1:]}Id",
                        "type": "Id",
                        "required": True,
                        "description": f"Primary {object_label} record Id.",
                        "object": primary_object if target_objects else None,
                    },
                    *field_inputs,
                    {
                        "name": "rationale",
                        "type": "String",
                        "required": False,
                        "description": "Human-readable reason for the writeback.",
                    },
                ],
                outputs=[
                    {
                        "name": "status",
                        "type": "String",
                        "required": True,
                        "description": "Writeback status.",
                    },
                    {
                        "name": "updatedFields",
                        "type": "String",
                        "required": False,
                        "description": "Comma-separated list of fields updated.",
                    },
                    {
                        "name": "rationale",
                        "type": "String",
                        "required": False,
                        "description": "Result rationale.",
                    },
                ],
                source_topics=all_topic_names,
                source_processes=source_process_rows,
                fallback_operation="update",
            )
        )
    elif any(
        set(_as_list(ref.get("operations"))).intersection({"create", "update", "delete"})
        for ref in mapped_refs
    ):
        write_refs = [
            binding
            for binding in object_bindings
            if set(_binding_permission(binding)).intersection({"create", "update", "delete"})
        ]
        action_contracts.append(
            _action_contract(
                name=f"Apply{stem}Decision",
                common_name=f"Apply {object_label} decision",
                purpose=f"Applies a bounded {agent_name} decision after analyst review.",
                capability_type="writeback",
                target_objects=target_objects,
                bindings=write_refs or validated[:1],
                inputs=[
                    {
                        "name": f"{object_label[:1].lower()}{object_label[1:]}Id",
                        "type": "Id",
                        "required": True,
                        "description": f"Primary {object_label} record Id.",
                        "object": primary_object if target_objects else None,
                    }
                ],
                outputs=[
                    {
                        "name": "status",
                        "type": "String",
                        "required": True,
                        "description": "Decision application status.",
                    }
                ],
                source_topics=all_topic_names,
                source_processes=source_process_rows,
                fallback_operation="update",
            )
        )

    topic_actions: dict[str, list[str]] = {name: [] for name in all_topic_names}
    for action in action_contracts:
        source_topics = _as_list(action.get("source_topics")) or all_topic_names
        for topic_name in source_topics:
            if topic_name in topic_actions:
                topic_actions[topic_name].append(action["name"])
    for topic_name in all_topic_names:
        if not topic_actions[topic_name] and action_contracts:
            topic_actions[topic_name].append(action_contracts[0]["name"])

    topics = []
    for topic in raw_topics:
        topic_name = _text(topic.get("topic_name"), "Agent Topic")
        topics.append(
            {
                "name": topic_name,
                "description": _text(topic.get("description"), "Agent topic generated from Arcflare analysis."),
                "reasoning_type": _text(topic.get("reasoning_type"), "hybrid"),
                "actions": sorted(dict.fromkeys(topic_actions.get(topic_name) or [])),
                "source_actions_needed": _as_list(topic.get("actions_needed")),
            }
        )

    return topics, action_contracts, blockers


def _metadata_grounding_from_bindings(context: dict, payload: dict) -> dict:
    labels = _metadata_labels(context)
    mapped = []
    validated_dependencies = []
    upstream_defects = []
    advisory_suggestions = []
    external_dependencies = []
    warnings = []
    for binding in _as_list(payload.get("bindings")):
        if not isinstance(binding, dict):
            continue
        status = _text(binding.get("status"))
        ref_type = _text(binding.get("ref_type"), "object")
        object_api_name = _text(binding.get("object_api_name"))
        api_name = _text(binding.get("api_name") or object_api_name)
        if status == "validated" and ref_type in {"object", "field"} and object_api_name:
            if not any(row["api_name"] == object_api_name for row in mapped):
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
            continue
        if status == "validated":
            validated_dependencies.append(
                {
                    "raw": _text(binding.get("raw_value"), api_name),
                    "status": "validated",
                    "ref_type": ref_type,
                    "api_name": api_name,
                    "object_api_name": object_api_name or None,
                    "operation": _text(binding.get("operation"), "execute"),
                    "source": _text(binding.get("source")),
                    "evidence_ids": _as_list(binding.get("evidence_ids")),
                }
            )
            continue
        if status:
            advisory_suggestions.append(
                {
                    "raw": _text(binding.get("raw_value"), api_name or "unknown"),
                    "status": status,
                    "ref_type": ref_type,
                    "api_name": api_name or None,
                    "source": _text(binding.get("source")),
                    "reason": _text(binding.get("reason"), "requires_process_evidence"),
                    "evidence_ids": _as_list(binding.get("evidence_ids")),
                }
            )

    for binding in _as_list(payload.get("unresolved_bindings")):
        if not isinstance(binding, dict):
            continue
        upstream_defects.append(
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

    for binding in _as_list(payload.get("advisory_bindings")):
        if not isinstance(binding, dict):
            continue
        advisory_suggestions.append(
            {
                "raw": _text(binding.get("raw_value"), binding.get("api_name") or "unknown"),
                "status": _text(binding.get("status"), "suggested"),
                "ref_type": _text(binding.get("ref_type"), "unknown"),
                "api_name": binding.get("api_name"),
                "object_api_name": binding.get("object_api_name"),
                "field_api_name": binding.get("field_api_name"),
                "source": _text(binding.get("source")),
                "reason": _text(binding.get("reason"), "requires_process_evidence"),
                "evidence_ids": _as_list(binding.get("evidence_ids")),
            }
        )

    for binding in _as_list(payload.get("unresolved_external_dependencies")):
        if not isinstance(binding, dict):
            continue
        external_dependencies.append(
            {
                "raw": _text(binding.get("raw_value"), binding.get("api_name") or "unknown"),
                "status": _text(binding.get("status"), "unresolved"),
                "ref_type": _text(binding.get("ref_type"), "external_system"),
                "api_name": binding.get("api_name"),
                "source": _text(binding.get("source")),
                "reason": _text(binding.get("reason"), "external_contract_required"),
                "evidence_ids": _as_list(binding.get("evidence_ids")),
            }
        )

    if upstream_defects:
        warnings.append("Upstream process evidence is incomplete; rerun assessment before source generation.")
    if external_dependencies:
        warnings.append("External dependencies need an integration contract before deployable source generation.")
    if advisory_suggestions:
        warnings.append("LLM suggestions are advisory only and are not used as source dependencies.")

    return {
        "binding_model_version": payload.get("binding_model_version") or payload.get("schema_version"),
        "mapped": mapped,
        "validated_dependencies": validated_dependencies,
        "upstream_defects": upstream_defects,
        "advisory_suggestions": advisory_suggestions,
        "external_dependencies": external_dependencies,
        "unresolved": [] if payload.get("schema_version") == "metadata_binding_manifest_v1" else upstream_defects,
        "legacy_suggestions": [],
        "legacy_adapter_used": False,
        "quality_gates": dict(payload.get("quality_gates") or {}),
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
        "validated_dependencies": [],
        "upstream_defects": [],
        "advisory_suggestions": [],
        "external_dependencies": [],
        "legacy_suggestions": _as_list(legacy.get("mapped")),
        "legacy_adapter_used": bool(raw_data_requirements),
        "quality_gates": {"agent_ready": False if raw_data_requirements else True},
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
    raw_topics = [topic for topic in _as_list(opportunity.get("topics")) if isinstance(topic, dict)]
    topics, action_contracts, planner_blockers = _planned_action_contracts(
        opportunity=opportunity,
        agent_name=agent_name,
        raw_topics=raw_topics,
        mapped_refs=_dedupe_objects(mapped_data_requirements),
        binding_payload=binding_payload,
    )

    permission_requirements = sorted(
        [
        {
            "object": obj["api_name"],
            "operations": _as_list(obj.get("operations")) or ["read"],
            "reason": "Required by validated metadata bindings for generated Agentforce action contracts.",
        }
        for obj in mapped_data_requirements
        if isinstance(obj, dict) and obj.get("api_name") in known_objects
        ],
        key=lambda row: row["object"],
    )
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
        "blockers": planner_blockers,
    }
    validation = validate_design_package(package, known_salesforce_objects=known_objects)
    package["blockers"] = validation["blockers"]
    package["warnings"] = validation["warnings"]
    return package
