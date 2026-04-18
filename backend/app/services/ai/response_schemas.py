"""Gemini response_schema definitions for structured output operations.

When passed to GenerateContentConfig alongside response_mime_type="application/json",
these schemas enable constrained decoding — the model is structurally unable to
return a shape that violates the schema. This replaces prompt-level "please return
this JSON" instructions with API-level enforcement.

Gemini response_schema supports a subset of JSON Schema:
  type, properties, required, items, enum, description, nullable
"""
from __future__ import annotations

DISCOVERY_DOMAIN_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "domains": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "confidence": {"type": "NUMBER"},
                    "associated_objects": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "associated_automations": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "associated_documents": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "actors": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "reasoning": {"type": "STRING"},
                },
                "required": ["name", "description", "confidence", "reasoning"],
            },
        },
    },
    "required": ["domains"],
}

DISCOVERY_STRUCTURE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "processes": {
            "type": "ARRAY",
            "description": "Flat list of ALL items at every level. Use parent_name to express hierarchy.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "level": {"type": "STRING", "enum": ["process", "subprocess", "step"]},
                    "parent_name": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Name of the parent process/subprocess. null for top-level processes.",
                    },
                    "description": {"type": "STRING"},
                    "narrative": {"type": "STRING"},
                    "confidence": {"type": "NUMBER"},
                    "needs_review": {"type": "BOOLEAN"},
                    "artifacts": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "type": {"type": "STRING", "enum": ["object", "flow", "validation_rule"]},
                                "api_name": {"type": "STRING"},
                            },
                            "required": ["type", "api_name"],
                        },
                    },
                    "actors": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["name", "level", "description", "confidence"],
            },
        },
    },
    "required": ["processes"],
}

_TRIGGER_CONDITION = {
    "type": "OBJECT",
    "properties": {
        "event": {"type": "STRING"},
        "condition": {"type": "STRING"},
        "source_object": {"type": "STRING"},
        "source_field": {"type": "STRING"},
    },
    "required": ["event"],
}

_DECISION_LOGIC = {
    "type": "OBJECT",
    "properties": {
        "rule": {"type": "STRING"},
        "outcome": {"type": "STRING"},
        "evidence": {"type": "STRING"},
    },
    "required": ["rule"],
}

_SYSTEM_TOUCHPOINT = {
    "type": "OBJECT",
    "properties": {
        "object_api_name": {"type": "STRING"},
        "fields": {"type": "ARRAY", "items": {"type": "STRING"}},
        "operation": {"type": "STRING", "enum": ["read", "write", "create"]},
        "automation_name": {"type": "STRING", "nullable": True},
    },
    "required": ["object_api_name", "operation"],
}

DISCOVERY_ENRICHMENT_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "enriched_steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "trigger_conditions": {"type": "ARRAY", "items": _TRIGGER_CONDITION},
                    "decision_logic": {"type": "ARRAY", "items": _DECISION_LOGIC},
                    "system_touchpoints": {"type": "ARRAY", "items": _SYSTEM_TOUCHPOINT},
                    "actors": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "type": {"type": "STRING", "enum": ["user", "integration", "system"]},
                            },
                            "required": ["name", "type"],
                        },
                    },
                    "success_criteria": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "criterion": {"type": "STRING"},
                                "measurable": {"type": "BOOLEAN"},
                            },
                            "required": ["criterion"],
                        },
                    },
                    "failure_modes": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "mode": {"type": "STRING"},
                                "impact": {"type": "STRING"},
                                "recovery": {"type": "STRING"},
                            },
                            "required": ["mode"],
                        },
                    },
                    "value_classification": {"type": "STRING", "enum": ["VA", "BVA", "NVA"]},
                    "complexity_score": {"type": "STRING", "enum": ["low", "medium", "high"]},
                    "automation_potential": {"type": "STRING", "enum": ["high", "medium", "low", "none"]},
                    "estimated_duration": {"type": "STRING", "enum": ["minutes", "hours", "days"]},
                    "estimated_frequency": {"type": "STRING", "enum": ["per_transaction", "daily", "weekly", "monthly"]},
                    "confidence": {"type": "NUMBER"},
                    "needs_review": {"type": "BOOLEAN"},
                },
                "required": ["name"],
            },
        },
    },
    "required": ["enriched_steps"],
}

DISCOVERY_FLOW_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "step_flows": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "source_step": {"type": "STRING"},
                    "target_step": {"type": "STRING"},
                    "condition": {"type": "STRING", "nullable": True},
                    "evidence": {"type": "STRING"},
                    "type": {"type": "STRING", "enum": ["automated", "manual", "integration", "inferred"]},
                },
                "required": ["source_step", "target_step", "type"],
            },
        },
        "parallel_groups": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "group_name": {"type": "STRING"},
                    "step_names": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["group_name", "step_names"],
            },
        },
        "handoffs": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "source": {"type": "STRING"},
                    "target": {"type": "STRING"},
                    "type": {"type": "STRING", "enum": ["integration", "manual", "automated", "unknown"]},
                    "description": {"type": "STRING"},
                    "confidence": {"type": "NUMBER"},
                    "data_transferred": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "object": {"type": "STRING"},
                                "fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["object"],
                        },
                    },
                    "transfer_mechanism": {"type": "STRING", "nullable": True},
                },
                "required": ["source", "target", "type"],
            },
        },
        "entry_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "terminal_points": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["step_flows"],
}

DISCOVERY_VALIDATION_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "critique": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "issue_type": {
                        "type": "STRING",
                        "enum": [
                            "orphaned_metadata", "phantom_reference", "structural",
                            "confidence_inflation", "missing_flow", "handoff_gap",
                        ],
                    },
                    "severity": {"type": "STRING", "enum": ["high", "medium", "low"]},
                    "description": {"type": "STRING"},
                    "affected_items": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "fix_applied": {"type": "STRING"},
                },
                "required": ["issue_type", "severity", "description"],
            },
        },
        "patches": {
            "type": "OBJECT",
            "properties": {
                "updated_steps": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                "removed_steps": {"type": "ARRAY", "items": {"type": "STRING"}},
                "confidence_adjustments": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "step_name": {"type": "STRING"},
                            "old": {"type": "NUMBER"},
                            "new": {"type": "NUMBER"},
                            "reason": {"type": "STRING"},
                        },
                        "required": ["step_name", "new"],
                    },
                },
            },
        },
    },
    "required": ["critique", "patches"],
}

DISCOVERY_SYNTHESIS_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "cross_domain_handoffs": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "source_domain": {"type": "STRING"},
                    "source_process": {"type": "STRING"},
                    "target_domain": {"type": "STRING"},
                    "target_process": {"type": "STRING"},
                    "type": {"type": "STRING", "enum": ["integration", "manual", "automated", "unknown"]},
                    "is_gap": {"type": "BOOLEAN"},
                    "confidence": {"type": "NUMBER"},
                    "reasoning": {"type": "STRING"},
                    "data_transferred": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "object": {"type": "STRING"},
                                "fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["object"],
                        },
                    },
                    "transfer_mechanism": {"type": "STRING", "nullable": True},
                },
                "required": ["source_process", "target_process", "type"],
            },
        },
        "orphaned_artifacts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type": {"type": "STRING", "enum": ["object", "automation"]},
                    "api_name": {"type": "STRING"},
                    "reasoning": {"type": "STRING"},
                },
                "required": ["type", "api_name"],
            },
        },
        "executive_summary": {"type": "STRING"},
    },
    "required": ["cross_domain_handoffs", "executive_summary"],
}


OPERATION_SCHEMAS: dict[str, dict] = {
    "discovery_domain": DISCOVERY_DOMAIN_SCHEMA,
    "discovery_structure": DISCOVERY_STRUCTURE_SCHEMA,
    "discovery_enrichment": DISCOVERY_ENRICHMENT_SCHEMA,
    "discovery_flow": DISCOVERY_FLOW_SCHEMA,
    "discovery_validation": DISCOVERY_VALIDATION_SCHEMA,
    "discovery_synthesis": DISCOVERY_SYNTHESIS_SCHEMA,
}


def get_response_schema(operation: str | None) -> dict | None:
    """Return the Gemini response_schema for an operation, or None if unschemaed."""
    if not operation:
        return None
    return OPERATION_SCHEMAS.get(operation)
