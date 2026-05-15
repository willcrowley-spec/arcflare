from app.services.ai.response_schemas import DISCOVERY_V2_EXTRACTION_SCHEMA
from app.services.processes.discovery import (
    _normalize_v2_extraction_result,
    _v2_extraction_contract_issues,
)
from app.services.prompts.seeds import (
    _DISCOVERY_V2_EXTRACTION_INSTRUCTIONS,
    _DISCOVERY_V2_EXTRACTION_PROTOCOL,
)


def test_v2_touchpoint_schema_carries_field_evidence():
    touchpoint_schema = DISCOVERY_V2_EXTRACTION_SCHEMA["$defs"]["touchpoint"]

    assert "fields" in touchpoint_schema["properties"]
    assert "fields" in touchpoint_schema["required"]


def test_v2_extraction_requires_child_steps():
    process_schema = DISCOVERY_V2_EXTRACTION_SCHEMA["$defs"]["process"]
    child_schema = DISCOVERY_V2_EXTRACTION_SCHEMA["$defs"]["child"]

    assert "children" in process_schema["required"]
    assert child_schema["properties"]["level"]["enum"] == ["step"]


def test_v2_extraction_schema_fits_cerebras_strict_budget():
    import json

    compact = json.dumps(DISCOVERY_V2_EXTRACTION_SCHEMA, separators=(",", ":"))

    assert len(compact) <= 5000


def test_v2_extraction_prompt_requires_object_field_touchpoints_and_leaf_steps():
    prompt_text = f"{_DISCOVERY_V2_EXTRACTION_INSTRUCTIONS}\n{_DISCOVERY_V2_EXTRACTION_PROTOCOL}"

    assert "Object.Field" in prompt_text
    assert "fields" in prompt_text
    assert "one child step" in prompt_text


def test_v2_normalization_adds_canonical_object_aliases_and_strips_object_prefix():
    parsed = {
        "processes": [
            {
                "name": "Case triage",
                "level": "process",
                "description": "Routes cases by priority.",
                "evidence_refs": ["OBJ-1"],
                "confidence": 0.8,
                "needs_review": False,
                "actors": [{"name": "Support", "type": "user", "evidence_refs": ["OBJ-1"]}],
                "trigger_conditions": [{"description": "Case created", "evidence_refs": ["OBJ-1"]}],
                "system_touchpoints": [
                    {
                        "name": "Case",
                        "type": "object",
                        "operation": "read",
                        "fields": ["Case.Priority", "Status"],
                        "evidence_refs": ["OBJ-1"],
                    }
                ],
                "value_classification": "BVA",
                "complexity_score": "medium",
                "automation_potential": "medium",
                "children": [
                    {
                        "name": "Read case context",
                        "level": "step",
                        "description": "Reads case fields.",
                        "evidence_refs": ["OBJ-1"],
                        "confidence": 0.8,
                        "needs_review": False,
                        "actors": [{"name": "Support", "type": "user", "evidence_refs": ["OBJ-1"]}],
                        "trigger_conditions": [{"description": "Case created", "evidence_refs": ["OBJ-1"]}],
                        "system_touchpoints": [
                            {
                                "name": "Case",
                                "type": "object",
                                "operation": "read",
                                "fields": ["Case.Priority"],
                                "evidence_refs": ["OBJ-1"],
                            }
                        ],
                        "value_classification": "BVA",
                        "complexity_score": "medium",
                        "automation_potential": "medium",
                    }
                ],
            }
        ]
    }

    normalized = _normalize_v2_extraction_result(parsed)
    process_touchpoint = normalized["processes"][0]["system_touchpoints"][0]
    step_touchpoint = normalized["processes"][0]["children"][0]["system_touchpoints"][0]

    assert process_touchpoint["object_api_name"] == "Case"
    assert process_touchpoint["fields"] == ["Priority", "Status"]
    assert step_touchpoint["object_api_name"] == "Case"
    assert step_touchpoint["fields"] == ["Priority"]
    assert _v2_extraction_contract_issues(normalized) == []


def test_v2_extraction_contract_blocks_processes_without_child_steps():
    parsed = {
        "processes": [
            {
                "name": "License management",
                "evidence_refs": ["OBJ-1"],
                "actors": [{"name": "Admin", "type": "user", "evidence_refs": ["OBJ-1"]}],
                "trigger_conditions": [{"description": "User change", "evidence_refs": ["OBJ-1"]}],
                "system_touchpoints": [
                    {"name": "User", "type": "object", "operation": "read", "fields": [], "evidence_refs": ["OBJ-1"]}
                ],
                "children": [],
            }
        ]
    }

    normalized = _normalize_v2_extraction_result(parsed)

    assert "License management:missing_child_steps" in _v2_extraction_contract_issues(normalized)
