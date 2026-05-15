from __future__ import annotations

import re
from collections.abc import Iterable

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _norm(value: object) -> str:
    return str(value or "").strip()


def _action_name(action: dict) -> str:
    return _norm(action.get("name")) or "unnamed_action"


def _object_names_from_contract(action: dict) -> set[str]:
    names: set[str] = set()
    for obj in _as_list(action.get("salesforce_objects")):
        name = _norm(obj)
        if name:
            names.add(name)
    for io in [*_as_list(action.get("inputs")), *_as_list(action.get("outputs"))]:
        if isinstance(io, dict):
            for key in ("object", "object_api_name", "source_object"):
                name = _norm(io.get(key))
                if name:
                    names.add(name)
    return names


def validate_design_package(
    design_package: dict,
    *,
    known_salesforce_objects: Iterable[str] | None = None,
) -> dict:
    """Validate an Agent Design Package before source generation.

    The validator is deliberately conservative. A blocker means Arcflare should
    not present generated Agentforce/Apex artifacts as deployable yet.
    """
    known = set(known_salesforce_objects or [])
    blockers: list[str] = [
        str(item) for item in _as_list(design_package.get("blockers")) if _norm(item)
    ]
    warnings: list[str] = []

    agent = design_package.get("agent") if isinstance(design_package.get("agent"), dict) else {}
    if not _norm(agent.get("name")):
        blockers.append("missing_agent_name")

    grounding = design_package.get("metadata_grounding") if isinstance(design_package.get("metadata_grounding"), dict) else {}
    if grounding.get("legacy_adapter_used"):
        warnings.append("legacy_string_adapter_used")
    for suggestion in _as_list(grounding.get("legacy_suggestions")):
        if not isinstance(suggestion, dict):
            continue
        api_name = _norm(suggestion.get("api_name")) or _norm(suggestion.get("raw")) or "unknown"
        blockers.append(f"legacy_binding_requires_review:{api_name}")
    for unresolved in _as_list(grounding.get("unresolved")):
        if not isinstance(unresolved, dict):
            continue
        raw = _norm(unresolved.get("raw")) or "unknown"
        status = _norm(unresolved.get("status"))
        if status == "suggested":
            blockers.append(f"suggested_metadata_binding:{raw}")
        else:
            blockers.append(f"unresolved_metadata_binding:{raw}")
    for defect in _as_list(grounding.get("upstream_defects")):
        if not isinstance(defect, dict):
            continue
        raw = _norm(defect.get("raw")) or _norm(defect.get("api_name")) or "unknown"
        blockers.append(f"upstream_metadata_evidence_missing:{raw}")
    for dependency in _as_list(grounding.get("external_dependencies")):
        if not isinstance(dependency, dict):
            continue
        raw = _norm(dependency.get("raw")) or _norm(dependency.get("api_name")) or "unknown"
        blockers.append(f"external_dependency_contract_missing:{raw}")
    for suggestion in _as_list(grounding.get("advisory_suggestions")):
        if isinstance(suggestion, dict):
            raw = _norm(suggestion.get("raw")) or _norm(suggestion.get("api_name")) or "unknown"
            warnings.append(f"advisory_metadata_suggestion_ignored:{raw}")

    topics = _as_list(design_package.get("topics"))
    if not topics:
        blockers.append("missing_topics")

    actions = [a for a in _as_list(design_package.get("action_contracts")) if isinstance(a, dict)]
    if not actions:
        blockers.append("missing_action_contracts")

    permission_requirements = [
        p for p in _as_list(design_package.get("permission_requirements")) if isinstance(p, dict)
    ]
    permission_objects = {_norm(p.get("object")) for p in permission_requirements if _norm(p.get("object"))}

    action_names = set()
    referenced_objects: set[str] = set()
    for action in actions:
        name = _action_name(action)
        if not _SAFE_NAME_RE.match(name):
            blockers.append(f"unsafe_action_name:{name}")
        if name in action_names:
            blockers.append(f"duplicate_action_contract:{name}")
        action_names.add(name)

        if not _norm(action.get("description")):
            warnings.append(f"missing_action_description:{name}")
        if not _as_list(action.get("inputs")):
            blockers.append(f"missing_action_inputs:{name}")
        if not _as_list(action.get("outputs")):
            blockers.append(f"missing_action_outputs:{name}")
        action_objects = _object_names_from_contract(action)
        if action_objects and not _as_list(action.get("permissions")):
            blockers.append(f"missing_action_permissions:{name}")

        for obj in action_objects:
            referenced_objects.add(obj)
            if known and obj not in known:
                blockers.append(f"unknown_salesforce_object:{obj}")

    for obj in sorted(referenced_objects):
        if obj not in permission_objects:
            blockers.append(f"missing_permission_requirement:{obj}")

    for integration in _as_list(design_package.get("integration_requirements")):
        if isinstance(integration, dict) and _norm(integration.get("status")) == "unresolved":
            blockers.append(f"unresolved_integration:{_norm(integration.get('name')) or 'unknown'}")
        elif isinstance(integration, str) and integration.strip():
            warnings.append(f"integration_requires_apex_middleware:{integration.strip()}")

    for topic in topics:
        if not isinstance(topic, dict):
            continue
        for action_name in _as_list(topic.get("actions")):
            if _norm(action_name) and _norm(action_name) not in action_names:
                blockers.append(f"topic_references_missing_action:{_norm(action_name)}")

    blockers = sorted(dict.fromkeys(blockers))
    warnings = sorted(dict.fromkeys(warnings))
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}
