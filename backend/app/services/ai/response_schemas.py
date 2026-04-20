"""JSON Schema definitions for structured output operations.

Used with LiteLLM's ``response_format`` parameter to enable constrained
decoding across providers (Anthropic, OpenAI, Gemini).  LiteLLM handles
the provider-specific translation automatically.

All schemas follow standard JSON Schema (lowercase types).
"""
from __future__ import annotations

DISCOVERY_DOMAIN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "domains": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                    "associated_objects": {"type": "array", "items": {"type": "string"}},
                    "associated_automations": {"type": "array", "items": {"type": "string"}},
                    "associated_documents": {"type": "array", "items": {"type": "string"}},
                    "actors": {"type": "array", "items": {"type": "string"}},
                    "reasoning": {"type": "string"},
                },
                "required": ["name", "description", "confidence", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["domains"],
    "additionalProperties": False,
}

DISCOVERY_STRUCTURE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "processes": {
            "type": "array",
            "description": "Flat list of ALL items at every level. Use parent_name to express hierarchy.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "level": {"type": "string", "enum": ["process", "subprocess", "step"]},
                    "parent_name": {
                        "type": ["string", "null"],
                        "description": "Name of the parent process/subprocess. null for top-level processes.",
                    },
                    "description": {"type": "string"},
                    "narrative": {"type": "string"},
                    "confidence": {"type": "number"},
                    "needs_review": {"type": "boolean"},
                    "artifacts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["object", "flow", "validation_rule"]},
                                "api_name": {"type": "string"},
                            },
                            "required": ["type", "api_name"],
                            "additionalProperties": False,
                        },
                    },
                    "actors": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "level", "description", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["processes"],
    "additionalProperties": False,
}

_TRIGGER_CONDITION = {
    "type": "object",
    "properties": {
        "event": {"type": "string"},
        "condition": {"type": "string"},
        "source_object": {"type": "string"},
        "source_field": {"type": "string"},
    },
    "required": ["event"],
    "additionalProperties": False,
}

_DECISION_LOGIC = {
    "type": "object",
    "properties": {
        "rule": {"type": "string"},
        "outcome": {"type": "string"},
        "evidence": {"type": "string"},
    },
    "required": ["rule"],
    "additionalProperties": False,
}

_SYSTEM_TOUCHPOINT = {
    "type": "object",
    "properties": {
        "object_api_name": {"type": "string"},
        "fields": {"type": "array", "items": {"type": "string"}},
        "operation": {"type": "string", "enum": ["read", "write", "create"]},
        "automation_name": {"type": ["string", "null"]},
    },
    "required": ["object_api_name", "operation"],
    "additionalProperties": False,
}

DISCOVERY_ENRICHMENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "enriched_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trigger_conditions": {"type": "array", "items": _TRIGGER_CONDITION},
                    "decision_logic": {"type": "array", "items": _DECISION_LOGIC},
                    "system_touchpoints": {"type": "array", "items": _SYSTEM_TOUCHPOINT},
                    "actors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["user", "integration", "system"]},
                            },
                            "required": ["name", "type"],
                            "additionalProperties": False,
                        },
                    },
                    "success_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "criterion": {"type": "string"},
                                "measurable": {"type": "boolean"},
                            },
                            "required": ["criterion"],
                            "additionalProperties": False,
                        },
                    },
                    "failure_modes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "mode": {"type": "string"},
                                "impact": {"type": "string"},
                                "recovery": {"type": "string"},
                            },
                            "required": ["mode"],
                            "additionalProperties": False,
                        },
                    },
                    "value_classification": {"type": "string", "enum": ["VA", "BVA", "NVA"]},
                    "complexity_score": {"type": "string", "enum": ["low", "medium", "high"]},
                    "automation_potential": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "estimated_duration": {"type": "string", "enum": ["minutes", "hours", "days"]},
                    "estimated_frequency": {"type": "string", "enum": ["per_transaction", "daily", "weekly", "monthly"]},
                    "confidence": {"type": "number"},
                    "needs_review": {"type": "boolean"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["enriched_steps"],
    "additionalProperties": False,
}

DISCOVERY_FLOW_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "step_flows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_step": {"type": "string"},
                    "target_step": {"type": "string"},
                    "condition": {"type": ["string", "null"]},
                    "evidence": {"type": "string"},
                    "type": {"type": "string", "enum": ["automated", "manual", "integration", "inferred"]},
                },
                "required": ["source_step", "target_step", "type"],
                "additionalProperties": False,
            },
        },
        "parallel_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "group_name": {"type": "string"},
                    "step_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["group_name", "step_names"],
                "additionalProperties": False,
            },
        },
        "handoffs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string", "enum": ["integration", "manual", "automated", "unknown"]},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                    "data_transferred": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "object": {"type": "string"},
                                "fields": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["object"],
                            "additionalProperties": False,
                        },
                    },
                    "transfer_mechanism": {"type": ["string", "null"]},
                },
                "required": ["source", "target", "type"],
                "additionalProperties": False,
            },
        },
        "entry_points": {"type": "array", "items": {"type": "string"}},
        "terminal_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["step_flows"],
    "additionalProperties": False,
}

DISCOVERY_VALIDATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "critique": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "enum": [
                            "orphaned_metadata", "phantom_reference", "structural",
                            "confidence_inflation", "missing_flow", "handoff_gap",
                        ],
                    },
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "description": {"type": "string"},
                    "affected_items": {"type": "array", "items": {"type": "string"}},
                    "fix_applied": {"type": "string"},
                },
                "required": ["issue_type", "severity", "description"],
                "additionalProperties": False,
            },
        },
        "patches": {
            "type": "object",
            "properties": {
                "updated_steps": {"type": "array", "items": {"type": "object"}},
                "removed_steps": {"type": "array", "items": {"type": "string"}},
                "confidence_adjustments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_name": {"type": "string"},
                            "old": {"type": "number"},
                            "new": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["step_name", "new"],
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
    },
    "required": ["critique", "patches"],
    "additionalProperties": False,
}

DISCOVERY_SYNTHESIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "cross_domain_handoffs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_domain": {"type": "string"},
                    "source_process": {"type": "string"},
                    "target_domain": {"type": "string"},
                    "target_process": {"type": "string"},
                    "type": {"type": "string", "enum": ["integration", "manual", "automated", "unknown"]},
                    "is_gap": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "data_transferred": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "object": {"type": "string"},
                                "fields": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["object"],
                            "additionalProperties": False,
                        },
                    },
                    "transfer_mechanism": {"type": ["string", "null"]},
                },
                "required": ["source_process", "target_process", "type"],
                "additionalProperties": False,
            },
        },
        "orphaned_artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["object", "automation"]},
                    "api_name": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["type", "api_name"],
                "additionalProperties": False,
            },
        },
        "executive_summary": {"type": "string"},
    },
    "required": ["cross_domain_handoffs", "executive_summary"],
    "additionalProperties": False,
}


DISCOVERY_ENRICHMENT_FLOW_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "enriched_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trigger_conditions": {"type": "array", "items": _TRIGGER_CONDITION},
                    "decision_logic": {"type": "array", "items": _DECISION_LOGIC},
                    "system_touchpoints": {"type": "array", "items": _SYSTEM_TOUCHPOINT},
                    "actors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["user", "integration", "system"]},
                            },
                            "required": ["name", "type"],
                            "additionalProperties": False,
                        },
                    },
                    "success_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "criterion": {"type": "string"},
                                "measurable": {"type": "boolean"},
                            },
                            "required": ["criterion"],
                            "additionalProperties": False,
                        },
                    },
                    "failure_modes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "mode": {"type": "string"},
                                "impact": {"type": "string"},
                                "recovery": {"type": "string"},
                            },
                            "required": ["mode"],
                            "additionalProperties": False,
                        },
                    },
                    "value_classification": {"type": "string", "enum": ["VA", "BVA", "NVA"]},
                    "complexity_score": {"type": "string", "enum": ["low", "medium", "high"]},
                    "automation_potential": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "estimated_duration": {"type": "string", "enum": ["minutes", "hours", "days"]},
                    "estimated_frequency": {"type": "string", "enum": ["per_transaction", "daily", "weekly", "monthly"]},
                    "confidence": {"type": "number"},
                    "needs_review": {"type": "boolean"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        "step_flows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_step": {"type": "string"},
                    "target_step": {"type": "string"},
                    "condition": {"type": ["string", "null"]},
                    "evidence": {"type": "string"},
                    "type": {"type": "string", "enum": ["automated", "manual", "integration", "inferred"]},
                },
                "required": ["source_step", "target_step", "type"],
                "additionalProperties": False,
            },
        },
        "parallel_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "group_name": {"type": "string"},
                    "step_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["group_name", "step_names"],
                "additionalProperties": False,
            },
        },
        "handoffs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string", "enum": ["integration", "manual", "automated", "unknown"]},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                    "data_transferred": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "object": {"type": "string"},
                                "fields": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["object"],
                            "additionalProperties": False,
                        },
                    },
                    "transfer_mechanism": {"type": ["string", "null"]},
                },
                "required": ["source", "target", "type"],
                "additionalProperties": False,
            },
        },
        "entry_points": {"type": "array", "items": {"type": "string"}},
        "terminal_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["enriched_steps", "step_flows"],
    "additionalProperties": False,
}


OPERATION_SCHEMAS: dict[str, dict] = {
    "discovery_domain": DISCOVERY_DOMAIN_SCHEMA,
    "discovery_structure": DISCOVERY_STRUCTURE_SCHEMA,
    "discovery_enrichment": DISCOVERY_ENRICHMENT_SCHEMA,
    "discovery_flow": DISCOVERY_FLOW_SCHEMA,
    "discovery_enrichment_flow": DISCOVERY_ENRICHMENT_FLOW_SCHEMA,
    "discovery_validation": DISCOVERY_VALIDATION_SCHEMA,
    "discovery_synthesis": DISCOVERY_SYNTHESIS_SCHEMA,
}


def get_response_schema(operation: str | None) -> dict | None:
    """Return the JSON Schema for an operation, or None if unschemaed."""
    if not operation:
        return None
    return OPERATION_SCHEMAS.get(operation)
