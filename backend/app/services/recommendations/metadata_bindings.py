"""Typed metadata bindings for recommendation-to-agent generation.

This module is the enterprise boundary between Arcflare's process evidence graph
and Salesforce source generation. LLM prose may describe what data an agent
needs, but only validated bindings produced here can become deployable
Agentforce/Apex dependencies.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

METADATA_BINDING_MODEL_VERSION = "metadata_bindings_v1"

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


def _lower_set(values: Iterable[str]) -> set[str]:
    return {v.lower() for v in values if v}


def _tokenize(value: str) -> set[str]:
    return {part for part in "".join(ch if ch.isalnum() else " " for ch in value.lower()).split() if part}


def _metadata_indexes(salesforce_metadata: Mapping[str, Any] | None) -> tuple[dict[str, dict], dict[str, set[str]]]:
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
    return object_index, field_index


def _touchpoint_object_and_fields(touchpoint: Any) -> tuple[str, list[str], str, str]:
    if isinstance(touchpoint, str):
        raw = _text(touchpoint)
        if "." in raw:
            obj, field = raw.split(".", 1)
            return _text(obj), [_text(field)], "read", raw
        return raw, [], "read", raw

    if isinstance(touchpoint, Mapping):
        raw = _text(touchpoint.get("raw")) or _text(touchpoint)
        obj = _text(
            touchpoint.get("object_api_name")
            or touchpoint.get("object")
            or touchpoint.get("sobject")
            or touchpoint.get("api_name")
        )
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
    match known Salesforce metadata. LLM data requirements are retained as
    suggested or unresolved mapping tasks.
    """
    opp = opportunity or {}
    object_index, field_index = _metadata_indexes(salesforce_metadata)
    bindings: list[dict] = []
    unresolved: list[dict] = []
    telemetry = {
        "bindings_from_process_touchpoints": 0,
        "bindings_from_step_touchpoints": 0,
        "bindings_from_metadata_inventory": 0,
        "bindings_from_llm_suggestions": 0,
        "bindings_from_legacy_adapter": 0,
        "unresolved_binding_count": 0,
    }

    for touchpoint, source, evidence in _iter_touchpoint_evidence(opp, process_contexts):
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
        raw_value = _text(suggestion.get("raw_value")) or _text(suggestion.get("object_api_name"))
        object_api_name = _text(suggestion.get("object_api_name"))
        operation = _text(suggestion.get("operation")) or "read"
        obj = object_index.get(object_api_name.lower()) if object_api_name else None
        if obj and obj["api_name"] not in bound_objects:
            bindings.append(
                _binding(
                    ref_type=_text(suggestion.get("ref_type")) or "object",
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
        elif raw_value and raw_value not in {row.get("raw_value") for row in unresolved}:
            unresolved.append(
                _binding(
                    ref_type=_text(suggestion.get("ref_type")) or _unresolved_ref_type(raw_value),
                    api_name=object_api_name or None,
                    object_api_name=object_api_name or None,
                    field_api_name=_text(suggestion.get("field_api_name")) or None,
                    operation=operation,
                    source="llm_suggestion",
                    confidence=0.3,
                    status=UNRESOLVED_STATUS,
                    raw_value=raw_value,
                    reason="requires_metadata_mapping",
                )
            )

    for raw in _as_list(opp.get("data_requirements")):
        raw_value = _text(raw)
        if not raw_value:
            continue
        if _covered_by_validated_binding(raw_value, bound_objects, object_index):
            continue
        obj = object_index.get(raw_value.lower())
        if obj and obj["api_name"] not in bound_objects:
            bindings.append(
                _binding(
                    ref_type="object",
                    api_name=obj["api_name"],
                    object_api_name=obj["api_name"],
                    operation="read",
                    source="llm_suggestion",
                    confidence=0.55,
                    status=SUGGESTED_STATUS,
                    raw_value=raw_value,
                    reason="llm_suggestion_requires_process_or_user_evidence",
                )
            )
            telemetry["bindings_from_llm_suggestions"] += 1
        elif not obj and raw_value not in {row.get("raw_value") for row in unresolved}:
            unresolved.append(
                _binding(
                    ref_type=_unresolved_ref_type(raw_value),
                    api_name=None,
                    object_api_name=None,
                    operation="read",
                    source="llm_suggestion",
                    confidence=0.3,
                    status=UNRESOLVED_STATUS,
                    raw_value=raw_value,
                    reason="requires_metadata_mapping",
                )
            )

    bindings = _dedupe(bindings)
    unresolved = _dedupe(unresolved)
    telemetry["unresolved_binding_count"] = len(unresolved)

    return {
        "schema_version": METADATA_BINDING_MODEL_VERSION,
        "binding_model_version": METADATA_BINDING_MODEL_VERSION,
        "bindings": bindings,
        "unresolved_bindings": unresolved,
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
        object_api_name = _text(binding.get("object_api_name") or binding.get("api_name"))
        if not object_api_name:
            continue
        existing = objects.get(object_api_name)
        if existing is None or binding.get("ref_type") == "object":
            objects[object_api_name] = dict(binding)
    return list(objects.values())
