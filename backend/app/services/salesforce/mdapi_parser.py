"""Deterministic parsers for Salesforce MDAPI XML (metadata namespace)."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any

MD_NS = "http://soap.sforce.com/2006/04/metadata"
NS = {"md": MD_NS}


def _text(elem: ET.Element | None, path: str) -> str | None:
    if elem is None:
        return None
    child = elem.find(path, NS)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _collect_objects_from_record_nodes(container: ET.Element, tag: str) -> list[str]:
    out: list[str] = []
    for node in container.findall(f"md:{tag}", NS):
        obj = _text(node, "md:object")
        if obj:
            out.append(obj)
    return out


def parse_flow(xml_bytes: bytes, filename: str) -> dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    process_type = _text(root, "md:processType")
    trigger_type = _text(root, "md:triggerType")
    status = _text(root, "md:status")
    description = _text(root, "md:description")

    start = root.find("md:start", NS)
    trigger_object: str | None = None
    if start is not None:
        trigger_object = _text(start, "md:object")
        if trigger_type is None:
            trigger_type = _text(start, "md:triggerType")

    decisions: list[dict[str, Any]] = []
    for dec in root.findall("md:decisions", NS):
        rules_out: list[dict[str, Any]] = []
        for rule in dec.findall("md:rules", NS):
            conds: list[dict[str, str | None]] = []
            for cond in rule.findall("md:conditions", NS):
                conds.append(
                    {
                        "field": _text(cond, "md:leftValueReference"),
                        "operator": _text(cond, "md:operator"),
                        "value": _text(cond, "md:rightValue/md:stringValue"),
                    }
                )
            tgt = rule.find("md:connector/md:targetReference", NS)
            connector = tgt.text.strip() if tgt is not None and tgt.text else None
            rules_out.append(
                {
                    "name": _text(rule, "md:name"),
                    "conditions": conds,
                    "connector": connector,
                }
            )
        def_tgt = dec.find("md:defaultConnector/md:targetReference", NS)
        default_connector = def_tgt.text.strip() if def_tgt is not None and def_tgt.text else None
        decisions.append(
            {
                "name": _text(dec, "md:name"),
                "label": _text(dec, "md:label"),
                "rules": rules_out,
                "default_connector": default_connector,
            }
        )

    def _record_fields(node: ET.Element) -> list[dict[str, str | None]]:
        fields: list[dict[str, str | None]] = []
        for ia in node.findall("md:inputAssignments", NS):
            fields.append(
                {
                    "field": _text(ia, "md:field"),
                    "value": _text(ia, "md:value/md:stringValue")
                    or _text(ia, "md:value/md:elementReference"),
                }
            )
        return fields

    record_lookups: list[dict[str, Any]] = []
    for node in root.findall("md:recordLookups", NS):
        record_lookups.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
                "connector": _text(node.find("md:connector", NS), "md:targetReference")
                if node.find("md:connector", NS) is not None
                else None,
            }
        )

    record_creates: list[dict[str, Any]] = []
    for node in root.findall("md:recordCreates", NS):
        record_creates.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
                "fields": _record_fields(node),
            }
        )

    record_updates: list[dict[str, Any]] = []
    for node in root.findall("md:recordUpdates", NS):
        record_updates.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
                "fields": _record_fields(node),
            }
        )

    record_deletes: list[dict[str, Any]] = []
    for node in root.findall("md:recordDeletes", NS):
        record_deletes.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
            }
        )

    assignments: list[dict[str, Any]] = []
    for node in root.findall("md:assignments", NS):
        assignments.append({"name": _text(node, "md:name")})

    screens: list[dict[str, Any]] = []
    for node in root.findall("md:screens", NS):
        screens.append({"name": _text(node, "md:name")})

    subflows: list[dict[str, Any]] = []
    for node in root.findall("md:subflows", NS):
        subflows.append(
            {
                "name": _text(node, "md:name"),
                "flow_name": _text(node, "md:flowName"),
            }
        )

    loops: list[dict[str, Any]] = []
    for node in root.findall("md:loops", NS):
        loops.append(
            {
                "name": _text(node, "md:name"),
                "collection": _text(node, "md:collectionReference"),
            }
        )

    action_calls: list[dict[str, Any]] = []
    for node in root.findall("md:actionCalls", NS):
        action_calls.append(
            {
                "name": _text(node, "md:name"),
                "action_type": _text(node, "md:actionType"),
                "action_name": _text(node, "md:actionName"),
            }
        )

    waits: list[dict[str, Any]] = []
    for node in root.findall("md:waits", NS):
        waits.append({"name": _text(node, "md:name")})

    variables: list[dict[str, Any]] = []
    for node in root.findall("md:variables", NS):
        variables.append(
            {
                "name": _text(node, "md:name"),
                "data_type": _text(node, "md:dataType"),
                "object_type": _text(node, "md:objectType"),
                "is_input": (_text(node, "md:isInput") or "").lower() == "true",
            }
        )

    formulas: list[dict[str, Any]] = []
    for node in root.findall("md:formulas", NS):
        formulas.append(
            {
                "name": _text(node, "md:name"),
                "expression": _text(node, "md:expression"),
                "data_type": _text(node, "md:dataType"),
            }
        )

    elements = {
        "decisions": decisions,
        "record_lookups": record_lookups,
        "record_creates": record_creates,
        "record_updates": record_updates,
        "record_deletes": record_deletes,
        "assignments": assignments,
        "screens": screens,
        "subflows": subflows,
        "loops": loops,
        "action_calls": action_calls,
        "waits": waits,
    }

    element_count = sum(len(v) for v in elements.values())
    branch_bonus = sum(len(d.get("rules", [])) for d in decisions)
    loop_bonus = len(loops) * 2
    complexity_score = element_count + branch_bonus + loop_bonus

    objects_touched: set[str] = set()
    if trigger_object:
        objects_touched.add(trigger_object)
    for tag in ("recordLookups", "recordCreates", "recordUpdates", "recordDeletes"):
        for obj in _collect_objects_from_record_nodes(root, tag):
            objects_touched.add(obj)
    for var in variables:
        ot = var.get("object_type")
        if ot:
            objects_touched.add(ot)

    raw_xml_hash = hashlib.sha256(xml_bytes).hexdigest()

    return {
        "process_type": process_type,
        "trigger_type": trigger_type,
        "trigger_object": trigger_object,
        "status": status,
        "description": description,
        "elements": elements,
        "variables": variables,
        "formulas": formulas,
        "element_count": element_count,
        "objects_touched": sorted(objects_touched),
        "complexity_score": complexity_score,
        "raw_xml_hash": raw_xml_hash,
        "source_filename": filename,
    }


def parse_custom_object(xml_bytes: bytes, filename: str) -> dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    sharing_model = _text(root, "md:sharingModel")

    validation_rules: list[dict[str, Any]] = []
    for vr in root.findall("md:validationRules", NS):
        validation_rules.append(
            {
                "name": _text(vr, "md:fullName"),
                "active": (_text(vr, "md:active") or "").lower() == "true",
                "description": _text(vr, "md:description"),
                "error_condition_formula": _text(vr, "md:errorConditionFormula"),
                "error_message": _text(vr, "md:errorMessage"),
                "error_display_field": _text(vr, "md:errorDisplayField"),
            }
        )

    formula_fields: list[dict[str, str | None]] = []
    for field in root.findall("md:fields", NS):
        formula = _text(field, "md:formula")
        if formula:
            formula_fields.append(
                {
                    "api_name": _text(field, "md:fullName"),
                    "formula": formula,
                    "formula_treat_blanks_as": _text(field, "md:formulaTreatBlanksAs"),
                }
            )

    record_types: list[dict[str, Any]] = []
    for rt in root.findall("md:recordTypes", NS):
        record_types.append(
            {
                "developer_name": _text(rt, "md:fullName"),
                "label": _text(rt, "md:label"),
                "active": (_text(rt, "md:active") or "").lower() == "true",
                "description": _text(rt, "md:description"),
            }
        )

    field_sets: list[dict[str, Any]] = []
    for fs in root.findall("md:fieldSets", NS):
        field_names = [_text(df, "md:field") for df in fs.findall("md:displayedFields", NS)]
        field_sets.append(
            {
                "label": _text(fs, "md:fullName"),
                "description": _text(fs, "md:description"),
                "fields": [f for f in field_names if f],
            }
        )

    list_views: list[dict[str, Any]] = []
    for lv in root.findall("md:listViews", NS):
        cols = [_text(c, "md:field") or (c.text or "").strip() for c in lv.findall("md:columns", NS)]
        cols = [c for c in cols if c]
        list_views.append(
            {
                "developer_name": _text(lv, "md:fullName"),
                "label": _text(lv, "md:label"),
                "filter_scope": _text(lv, "md:filterScope"),
                "filters": [],
                "columns": cols,
            }
        )

    web_links: list[dict[str, Any]] = []
    for wl in root.findall("md:webLinks", NS):
        web_links.append(
            {
                "name": _text(wl, "md:fullName"),
                "link_type": "url",
                "url_or_page": _text(wl, "md:url"),
            }
        )

    return {
        "validation_rules": validation_rules,
        "formula_fields": formula_fields,
        "record_types": record_types,
        "field_sets": field_sets,
        "list_views": list_views,
        "web_links": web_links,
        "sharing_model": sharing_model,
        "raw_xml_hash": hashlib.sha256(xml_bytes).hexdigest(),
        "source_filename": filename,
    }


def parse_workflow(xml_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    """Return one dict per workflow rule (automation row shape)."""
    root = ET.fromstring(xml_bytes)
    related_object = filename.split("/")[-1].replace(".workflow-meta.xml", "")

    field_updates_by_name: dict[str, dict[str, Any]] = {}
    for fu in root.findall("md:fieldUpdates", NS):
        name = _text(fu, "md:fullName")
        if name:
            field_updates_by_name[name] = {
                "name": name,
                "field": _text(fu, "md:field"),
                "value": _text(fu, "md:literalValue"),
                "formula": _text(fu, "md:formula"),
                "target_object": related_object,
            }

    email_alerts: dict[str, dict[str, Any]] = {}
    for al in root.findall("md:alerts", NS):
        name = _text(al, "md:fullName")
        if name:
            email_alerts[name] = {
                "name": name,
                "template": _text(al, "md:template"),
                "recipients": [],
            }

    outbound_messages: dict[str, dict[str, Any]] = {}
    for om in root.findall("md:outboundMessages", NS):
        name = _text(om, "md:fullName")
        if name:
            fields = [_text(f, "md:field") for f in om.findall("md:fields", NS)]
            fields = [f for f in fields if f]
            outbound_messages[name] = {
                "name": name,
                "endpoint_url": _text(om, "md:endpointUrl"),
                "fields": fields,
            }

    tasks: dict[str, dict[str, Any]] = {}
    for tk in root.findall("md:tasks", NS):
        name = _text(tk, "md:fullName")
        if name:
            tasks[name] = {
                "name": name,
                "subject": _text(tk, "md:subject"),
                "assignee": _text(tk, "md:assignedToType"),
                "due_date_offset": _text(tk, "md:offsetFromField"),
            }

    results: list[dict[str, Any]] = []
    for rule in root.findall("md:rules", NS):
        rule_name = _text(rule, "md:fullName")
        actions_out: dict[str, list[dict[str, str | None]]] = {
            "field_updates": [],
            "email_alerts": [],
            "outbound_messages": [],
            "tasks": [],
        }
        linkages: list[dict[str, str | None]] = []
        for act in rule.findall("md:actions", NS):
            an = _text(act, "md:name")
            at = _text(act, "md:type")
            linkages.append({"name": an, "type": at})
            if at == "FieldUpdate" and an in field_updates_by_name:
                actions_out["field_updates"].append(field_updates_by_name[an])
            elif at in ("Alert", "EmailAlert") and an in email_alerts:
                actions_out["email_alerts"].append(email_alerts[an])
            elif at == "OutboundMessage" and an in outbound_messages:
                actions_out["outbound_messages"].append(outbound_messages[an])
            elif at == "Task" and an in tasks:
                actions_out["tasks"].append(tasks[an])

        criteria_items: list[dict[str, str | None]] = []
        for crit in rule.findall("md:criteriaItems", NS):
            criteria_items.append(
                {
                    "field": _text(crit, "md:field"),
                    "operation": _text(crit, "md:operation"),
                    "value": _text(crit, "md:value"),
                }
            )

        results.append(
            {
                "automation_subtype": "workflow_rule",
                "api_name": rule_name,
                "active": (_text(rule, "md:active") or "").lower() == "true",
                "description": _text(rule, "md:description"),
                "criteria": {
                    "formula": _text(rule, "md:formula"),
                    "trigger_type": _text(rule, "md:triggerType"),
                    "criteria_items": criteria_items,
                },
                "actions": actions_out,
                "rule_action_linkages": linkages,
                "related_object": related_object,
                "raw_xml_hash": hashlib.sha256(xml_bytes).hexdigest(),
                "source_filename": filename,
            }
        )
    return results
