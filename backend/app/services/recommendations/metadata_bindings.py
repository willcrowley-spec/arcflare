"""Typed metadata bindings for recommendation-to-agent generation.

This module is the enterprise boundary between Arcflare's process evidence graph
and Salesforce source generation. LLM prose may describe what data an agent
needs, but only validated bindings produced here can become deployable
Agentforce/Apex dependencies.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

METADATA_BINDING_MODEL_VERSION = "metadata_binding_manifest_v1"
LEGACY_METADATA_BINDING_MODEL_VERSION = "metadata_bindings_v1"

VALID_BINDING_SOURCES = {
    "process_touchpoint",
    "step_touchpoint",
    "metadata_inventory",
    "llm_suggestion",
    "user_override",
    "legacy_string_adapter",
}

VALIDATED_STATUS = "validated"
SUGGESTED_STATUS = "suggested"
UNRESOLVED_STATUS = "unresolved"


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clean_api_name(value: Any) -> str:
    raw = _text(value)
    raw = raw.split("(", 1)[0].strip()
    return raw


def _lower_set(values: Iterable[str]) -> set[str]:
    return {v.lower() for v in values if v}


def _tokenize(value: str) -> set[str]:
    return {part for part in "".join(ch if ch.isalnum() else " " for ch in value.lower()).split() if part}


def _component_ref_type(value: str | None) -> str:
    raw = _text(value).lower()
    if "flow" in raw:
        return "flow"
    if "apex" in raw or "class" in raw:
        return "apex"
    if "prompt" in raw:
        return "prompt"
    return "flow"


def _metadata_indexes(
    salesforce_metadata: Mapping[str, Any] | None,
) -> tuple[dict[str, dict], dict[str, set[str]], dict[str, dict], dict[str, dict]]:
    metadata = salesforce_metadata or {}
    objects = _as_list(metadata.get("objects"))
    object_index: dict[str, dict] = {}
    field_index: dict[str, set[str]] = {}
    for item in objects:
        if not isinstance(item, Mapping):
            continue
        api_name = _text(item.get("api_name"))
        if not api_name:
            continue
        object_index[api_name.lower()] = {
            "api_name": api_name,
            "label": _text(item.get("label")) or api_name,
        }
        fields = set()
        for field in _as_list(item.get("fields")):
            if isinstance(field, Mapping):
                field_api_name = _text(field.get("api_name"))
            else:
                field_api_name = _text(field)
            if field_api_name:
                fields.add(field_api_name)
        field_index[api_name.lower()] = fields

    automation_index: dict[str, dict] = {}
    for item in _as_list(metadata.get("automations")):
        if not isinstance(item, Mapping):
            continue
        api_name = _text(item.get("api_name") or item.get("name"))
        if not api_name:
            continue
        automation_index[api_name.lower()] = {
            "api_name": api_name,
            "label": _text(item.get("label")) or api_name,
            "ref_type": _component_ref_type(_text(item.get("type") or item.get("automation_type"))),
            "related_object": _text(item.get("related_object")) or None,
            "status": _text(item.get("status")) or None,
        }

    component_index: dict[str, dict] = {}
    for item in _as_list(metadata.get("components")):
        if not isinstance(item, Mapping):
            continue
        api_name = _text(item.get("api_name") or item.get("name"))
        if not api_name:
            continue
        component_index[api_name.lower()] = {
            "api_name": api_name,
            "label": _text(item.get("label")) or api_name,
            "ref_type": _component_ref_type(_text(item.get("category") or item.get("component_category"))),
            "related_object": _text(item.get("related_object")) or None,
            "status": _text(item.get("status")) or None,
        }
    return object_index, field_index, automation_index, component_index


def _touchpoint_kind(touchpoint: Any) -> str:
    if isinstance(touchpoint, Mapping):
        return _text(touchpoint.get("type") or touchpoint.get("ref_type")).lower()
    return ""


def _touchpoint_name(touchpoint: Any) -> str:
    if isinstance(touchpoint, Mapping):
        return _clean_api_name(
            touchpoint.get("name")
            or touchpoint.get("api_name")
            or touchpoint.get("automation_name")
            or touchpoint.get("flow_api_name")
            or touchpoint.get("component_api_name")
            or touchpoint.get("raw")
        )
    return _text(touchpoint)


def _is_automation_touchpoint(touchpoint: Any) -> bool:
    kind = _touchpoint_kind(touchpoint)
    return kind in {"automation", "flow", "apex", "apex_class", "prompt", "component"}


def _is_external_touchpoint(touchpoint: Any) -> bool:
    kind = _touchpoint_kind(touchpoint)
    return kind in {"external_system", "external", "integration", "api", "queue", "schema_mapping"}


def _touchpoint_object_and_fields(touchpoint: Any) -> tuple[str, list[str], str, str]:
    if isinstance(touchpoint, str):
        raw = _text(touchpoint)
        if "." in raw:
            obj, field = raw.split(".", 1)
            return _text(obj), [_text(field)], "read", raw
        return raw, [], "read", raw

    if isinstance(touchpoint, Mapping):
        name = _touchpoint_name(touchpoint)
        touchpoint_type = _text(touchpoint.get("type")).lower()
        obj = _clean_api_name(
            touchpoint.get("object_api_name")
            or touchpoint.get("object")
            or touchpoint.get("sobject")
            or touchpoint.get("api_name")
        )
        if not obj and touchpoint_type in {"object", "sobject", "metadata_object"}:
            obj = name
        field_values: list[str] = []
        for key in ("field_api_name", "field"):
            value = _text(touchpoint.get(key))
            if value:
                field_values.append(value)
        for value in _as_list(touchpoint.get("fields")):
            field = _text(value.get("api_name") if isinstance(value, Mapping) else value)
            if field:
                field_values.append(field)
        operation = _text(touchpoint.get("operation")) or "read"
        raw = _text(touchpoint.get("raw")) or name or obj
        return obj, sorted(dict.fromkeys(field_values)), operation, raw

    raw = _text(touchpoint)
    return raw, [], "read", raw


def _replacement_ids(opportunity: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    process_ids: set[str] = set()
    step_ids: set[str] = set()
    for replacement in _as_list(opportunity.get("replaces")):
        if not isinstance(replacement, Mapping):
            continue
        pid = _text(replacement.get("process_id"))
        if pid:
            process_ids.add(pid)
        for sid in _as_list(replacement.get("step_ids")):
            value = _text(sid)
            if value:
                step_ids.add(value)
    return process_ids, step_ids


def _iter_touchpoint_evidence(
    opportunity: Mapping[str, Any],
    process_contexts: Iterable[Mapping[str, Any]] | None,
) -> Iterable[tuple[Any, str, dict]]:
    process_ids, step_ids = _replacement_ids(opportunity)
    if not process_ids and not step_ids:
        return []

    rows = []
    for process in process_contexts or []:
        if not isinstance(process, Mapping):
            continue
        process_id = _text(process.get("id"))
        if process_id and process_id in process_ids:
            for touchpoint in _as_list(process.get("system_touchpoints")):
                rows.append(
                    (
                        touchpoint,
                        "process_touchpoint",
                        {
                            "process_id": process_id,
                            "process_name": _text(process.get("name")),
                        },
                    )
                )
        for step in _as_list(process.get("steps")):
            if not isinstance(step, Mapping):
                continue
            step_id = _text(step.get("id"))
            if step_id and step_id in step_ids:
                for touchpoint in _as_list(step.get("system_touchpoints")):
                    rows.append(
                        (
                            touchpoint,
                            "step_touchpoint",
                            {
                                "process_id": process_id,
                                "process_name": _text(process.get("name")),
                                "step_id": step_id,
                                "step_name": _text(step.get("name")),
                            },
                        )
                    )
    return rows


def _covered_by_validated_binding(raw_value: str, bound_objects: set[str], object_index: Mapping[str, dict]) -> bool:
    raw_tokens = _tokenize(raw_value)
    if not raw_tokens:
        return False
    for object_api_name in bound_objects:
        obj = object_index.get(str(object_api_name).lower())
        aliases = [str(object_api_name)]
        if obj:
            aliases.append(str(obj.get("label") or ""))
        for alias in aliases:
            alias_tokens = _tokenize(alias.replace("__c", "").replace("__mdt", "").replace("_", " "))
            if alias_tokens and alias_tokens.issubset(raw_tokens):
                return True
    return False


def _covered_by_validated_dependency(
    suggestion: Mapping[str, Any],
    *,
    bindings: Iterable[Mapping[str, Any]],
    object_index: Mapping[str, dict],
    automation_index: Mapping[str, dict],
    component_index: Mapping[str, dict],
) -> bool:
    raw_value = _text(suggestion.get("raw_value"))
    object_api_name = _text(suggestion.get("object_api_name"))
    field_api_name = _text(suggestion.get("field_api_name"))
    api_name = _text(suggestion.get("api_name")) or raw_value
    validated = [b for b in bindings if b.get("status") == VALIDATED_STATUS]
    for binding in validated:
        binding_api = _text(binding.get("api_name"))
        binding_object = _text(binding.get("object_api_name"))
        binding_field = _text(binding.get("field_api_name"))
        if api_name and binding_api and api_name.lower() == binding_api.lower():
            return True
        if object_api_name and binding_object and object_api_name.lower() == binding_object.lower():
            if not field_api_name or field_api_name.lower() == binding_field.lower():
                return True

    bound_objects = {_text(b.get("object_api_name")) for b in validated if _text(b.get("object_api_name"))}
    if raw_value and _covered_by_validated_binding(raw_value, bound_objects, object_index):
        return True

    raw_lower = raw_value.lower()
    if raw_lower in automation_index or raw_lower in component_index:
        return any(_text(b.get("api_name")).lower() == raw_lower for b in validated)
    return False


def _evidence_ids(evidence: Mapping[str, Any]) -> list[str]:
    ids = []
    if evidence.get("process_id"):
        ids.append(f"process:{evidence['process_id']}")
    if evidence.get("step_id"):
        ids.append(f"step:{evidence['step_id']}")
    return ids


def _binding(
    *,
    ref_type: str,
    api_name: str | None,
    object_api_name: str | None,
    field_api_name: str | None = None,
    operation: str = "read",
    source: str,
    confidence: float,
    status: str,
    evidence: Mapping[str, Any] | None = None,
    raw_value: str | None = None,
    reason: str | None = None,
) -> dict:
    evidence = evidence or {}
    row = {
        "ref_type": ref_type,
        "api_name": api_name,
        "object_api_name": object_api_name,
        "field_api_name": field_api_name,
        "operation": operation or "read",
        "source": source,
        "confidence": round(float(confidence), 3),
        "status": status,
        "evidence_ids": _evidence_ids(evidence),
        "evidence": dict(evidence),
    }
    if raw_value:
        row["raw_value"] = raw_value
    if reason:
        row["reason"] = reason
    return row


def _unresolved_ref_type(raw_value: str) -> str:
    raw = raw_value.lower()
    if "queue" in raw or "roster" in raw or "team" in raw:
        return "queue"
    if "contract" in raw or "agreement" in raw:
        return "contract"
    if "schema" in raw or "field mapping" in raw or "mapping" in raw:
        return "schema_mapping"
    if "system" in raw or "integration" in raw or "api" in raw:
        return "external_system"
    return "object"


def _dedupe(rows: Iterable[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        key = (
            row.get("ref_type"),
            row.get("api_name"),
            row.get("object_api_name"),
            row.get("field_api_name"),
            row.get("operation"),
            row.get("source"),
            tuple(row.get("evidence_ids") or []),
            row.get("raw_value"),
            row.get("reason"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_metadata_bindings(
    opportunity: Mapping[str, Any] | None,
    *,
    process_contexts: Iterable[Mapping[str, Any]] | None = None,
    salesforce_metadata: Mapping[str, Any] | None = None,
) -> dict:
    """Build versioned, evidence-backed metadata bindings for a recommendation.

    Validated bindings come only from structured process/step touchpoints that
    match known Salesforce metadata. LLM suggestions are retained as advisory
    diagnostics only; data requirements remain display copy.
    """
    opp = opportunity or {}
    object_index, field_index, automation_index, component_index = _metadata_indexes(salesforce_metadata)
    bindings: list[dict] = []
    unresolved: list[dict] = []
    advisory: list[dict] = []
    external_dependencies: list[dict] = []
    telemetry = {
        "bindings_from_process_touchpoints": 0,
        "bindings_from_step_touchpoints": 0,
        "bindings_from_metadata_inventory": 0,
        "bindings_from_llm_suggestions": 0,
        "bindings_from_legacy_adapter": 0,
        "unresolved_binding_count": 0,
    }

    for touchpoint, source, evidence in _iter_touchpoint_evidence(opp, process_contexts):
        if _is_external_touchpoint(touchpoint):
            raw_value = _touchpoint_name(touchpoint)
            external_dependencies.append(
                _binding(
                    ref_type=_touchpoint_kind(touchpoint) or _unresolved_ref_type(raw_value),
                    api_name=raw_value or None,
                    object_api_name=None,
                    operation=_text(touchpoint.get("operation")) if isinstance(touchpoint, Mapping) else "read",
                    source=source,
                    confidence=1.0,
                    status=UNRESOLVED_STATUS,
                    evidence=evidence,
                    raw_value=raw_value,
                    reason="external_contract_required",
                )
            )
            continue

        if _is_automation_touchpoint(touchpoint):
            raw_value = _touchpoint_name(touchpoint)
            operation = (
                _text(touchpoint.get("operation")) if isinstance(touchpoint, Mapping) else "execute"
            ) or "execute"
            component = automation_index.get(raw_value.lower()) or component_index.get(raw_value.lower())
            if component is None:
                unresolved.append(
                    _binding(
                        ref_type=_touchpoint_kind(touchpoint) or "flow",
                        api_name=raw_value or None,
                        object_api_name=None,
                        operation=operation,
                        source=source,
                        confidence=1.0,
                        status=UNRESOLVED_STATUS,
                        evidence=evidence,
                        raw_value=raw_value,
                        reason="unknown_automation",
                    )
                )
                continue
            bindings.append(
                _binding(
                    ref_type=component["ref_type"],
                    api_name=component["api_name"],
                    object_api_name=component.get("related_object"),
                    operation=operation,
                    source=source,
                    confidence=1.0,
                    status=VALIDATED_STATUS,
                    evidence=evidence,
                    raw_value=raw_value,
                )
            )
            telemetry[f"bindings_from_{source}s"] += 1
            continue

        obj_raw, fields, operation, raw_value = _touchpoint_object_and_fields(touchpoint)
        obj = object_index.get(obj_raw.lower())
        if obj is None:
            unresolved.append(
                _binding(
                    ref_type="object",
                    api_name=obj_raw or None,
                    object_api_name=obj_raw or None,
                    operation=operation,
                    source=source,
                    confidence=1.0,
                    status=UNRESOLVED_STATUS,
                    evidence=evidence,
                    raw_value=raw_value,
                    reason="unknown_object",
                )
            )
            continue

        object_binding = _binding(
            ref_type="object",
            api_name=obj["api_name"],
            object_api_name=obj["api_name"],
            operation=operation,
            source=source,
            confidence=1.0,
            status=VALIDATED_STATUS,
            evidence=evidence,
            raw_value=raw_value,
        )
        bindings.append(object_binding)
        telemetry[f"bindings_from_{source}s"] += 1

        known_fields = field_index.get(obj["api_name"].lower(), set())
        known_fields_lower = _lower_set(known_fields)
        for field in fields:
            if not known_fields:
                unresolved.append(
                    _binding(
                        ref_type="field",
                        api_name=f"{obj['api_name']}.{field}",
                        object_api_name=obj["api_name"],
                        field_api_name=field,
                        operation=operation,
                        source=source,
                        confidence=1.0,
                        status=UNRESOLVED_STATUS,
                        evidence=evidence,
                        raw_value=raw_value,
                        reason="field_inventory_missing",
                    )
                )
                continue
            if field.lower() not in known_fields_lower:
                unresolved.append(
                    _binding(
                        ref_type="field",
                        api_name=f"{obj['api_name']}.{field}",
                        object_api_name=obj["api_name"],
                        field_api_name=field,
                        operation=operation,
                        source=source,
                        confidence=1.0,
                        status=UNRESOLVED_STATUS,
                        evidence=evidence,
                        raw_value=raw_value,
                        reason="unknown_field",
                    )
                )
                continue
            canonical_field = next((f for f in known_fields if f.lower() == field.lower()), field)
            bindings.append(
                _binding(
                    ref_type="field",
                    api_name=f"{obj['api_name']}.{canonical_field}",
                    object_api_name=obj["api_name"],
                    field_api_name=canonical_field,
                    operation=operation,
                    source=source,
                    confidence=1.0,
                    status=VALIDATED_STATUS,
                    evidence=evidence,
                    raw_value=raw_value,
                )
            )
            telemetry[f"bindings_from_{source}s"] += 1

    bound_objects = {
        row["object_api_name"]
        for row in bindings
        if row.get("status") == VALIDATED_STATUS and row.get("object_api_name")
    }
    for suggestion in _as_list(opp.get("suggested_metadata_refs")):
        if not isinstance(suggestion, Mapping):
            continue
        if _covered_by_validated_dependency(
            suggestion,
            bindings=bindings,
            object_index=object_index,
            automation_index=automation_index,
            component_index=component_index,
        ):
            continue
        raw_value = _text(suggestion.get("raw_value")) or _text(suggestion.get("object_api_name"))
        object_api_name = _text(suggestion.get("object_api_name"))
        operation = _text(suggestion.get("operation")) or "read"
        ref_type = _text(suggestion.get("ref_type")) or _unresolved_ref_type(raw_value)
        obj = object_index.get(object_api_name.lower()) if object_api_name else None
        component = (
            automation_index.get(raw_value.lower())
            or component_index.get(raw_value.lower())
            or automation_index.get(_text(suggestion.get("api_name")).lower())
            or component_index.get(_text(suggestion.get("api_name")).lower())
        )
        if obj and obj["api_name"] not in bound_objects:
            advisory.append(
                _binding(
                    ref_type=ref_type or "object",
                    api_name=obj["api_name"],
                    object_api_name=obj["api_name"],
                    field_api_name=_text(suggestion.get("field_api_name")) or None,
                    operation=operation,
                    source="llm_suggestion",
                    confidence=0.6,
                    status=SUGGESTED_STATUS,
                    raw_value=raw_value,
                    reason=_text(suggestion.get("reason")) or "llm_suggestion_requires_process_or_user_evidence",
                )
            )
            telemetry["bindings_from_llm_suggestions"] += 1
        elif component:
            advisory.append(
                _binding(
                    ref_type=component["ref_type"],
                    api_name=component["api_name"],
                    object_api_name=component.get("related_object"),
                    field_api_name=_text(suggestion.get("field_api_name")) or None,
                    operation=operation,
                    source="llm_suggestion",
                    confidence=0.6,
                    status=SUGGESTED_STATUS,
                    raw_value=raw_value,
                    reason=_text(suggestion.get("reason")) or "llm_suggestion_requires_process_or_user_evidence",
                )
            )
            telemetry["bindings_from_llm_suggestions"] += 1
        elif raw_value:
            advisory.append(
                _binding(
                    ref_type=ref_type,
                    api_name=object_api_name or None,
                    object_api_name=object_api_name or None,
                    field_api_name=_text(suggestion.get("field_api_name")) or None,
                    operation=operation,
                    source="llm_suggestion",
                    confidence=0.3,
                    status=SUGGESTED_STATUS,
                    raw_value=raw_value,
                    reason="llm_suggestion_requires_process_or_user_evidence",
                )
            )
            telemetry["bindings_from_llm_suggestions"] += 1

    bindings = _dedupe(bindings)
    unresolved = _dedupe(unresolved)
    advisory = _dedupe(advisory)
    external_dependencies = _dedupe(external_dependencies)
    telemetry["unresolved_binding_count"] = len(unresolved)
    telemetry["advisory_binding_count"] = len(advisory)
    telemetry["unresolved_external_dependency_count"] = len(external_dependencies)

    missing_evidence = [
        row.get("raw_value") or row.get("api_name") or row.get("object_api_name") or "unknown"
        for row in unresolved
    ]
    unresolved_external = [
        row.get("raw_value") or row.get("api_name") or "unknown"
        for row in external_dependencies
    ]

    return {
        "schema_version": METADATA_BINDING_MODEL_VERSION,
        "binding_model_version": METADATA_BINDING_MODEL_VERSION,
        "bindings": bindings,
        "advisory_bindings": advisory,
        "unresolved_bindings": unresolved,
        "unresolved_external_dependencies": external_dependencies,
        "quality_gates": {
            "agent_ready": not missing_evidence and not unresolved_external,
            "missing_evidence": missing_evidence,
            "unresolved_external_dependencies": unresolved_external,
        },
        "telemetry": telemetry,
    }


def validated_object_bindings(payload: Mapping[str, Any] | None) -> list[dict]:
    """Return unique validated Salesforce object bindings from a binding payload."""
    payload = payload or {}
    objects: dict[str, dict] = {}
    for binding in _as_list(payload.get("bindings")):
        if not isinstance(binding, Mapping):
            continue
        if binding.get("status") != VALIDATED_STATUS:
            continue
        if _text(binding.get("ref_type")) not in {"object", "field"}:
            continue
        object_api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if not object_api_name:
            continue
        existing = objects.get(object_api_name)
        if existing is None or binding.get("ref_type") == "object":
            objects[object_api_name] = dict(binding)
    return list(objects.values())
