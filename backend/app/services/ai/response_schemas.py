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
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
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


_EVIDENCE_REF = {"type": "string", "description": "Tagged ref like OBJ-1, AUTO-3, DOC-5"}

_EVIDENCE_REF_ARRAY = {"type": "array", "items": _EVIDENCE_REF}

_V2_ACTOR = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "enum": ["user", "integration", "system"]},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

_V2_TRIGGER = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
    },
    "required": ["description"],
    "additionalProperties": False,
}

_V2_TOUCHPOINT = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "enum": ["object", "automation", "component", "integration"]},
        "operation": {"type": "string", "enum": ["read", "write", "create", "trigger"]},
        "fields": {"type": "array", "items": {"type": "string"}},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

_V2_DECISION = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
    },
    "required": ["description"],
    "additionalProperties": False,
}

_V2_SUCCESS = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
    },
    "required": ["description"],
    "additionalProperties": False,
}

_V2_FAILURE = {
    "type": "object",
    "properties": {
        "mode": {"type": "string"},
        "impact": {"type": "string"},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
    },
    "required": ["mode"],
    "additionalProperties": False,
}

_V2_CHILD = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "level": {"type": "string", "enum": ["subprocess", "step"]},
        "description": {"type": "string"},
        "evidence_refs": _EVIDENCE_REF_ARRAY,
        "actors": {"type": "array", "items": _V2_ACTOR},
        "trigger_conditions": {"type": "array", "items": _V2_TRIGGER},
        "system_touchpoints": {"type": "array", "items": _V2_TOUCHPOINT},
        "decision_logic": {"type": "array", "items": _V2_DECISION},
        "success_criteria": {"type": "array", "items": _V2_SUCCESS},
        "failure_modes": {"type": "array", "items": _V2_FAILURE},
        "value_classification": {"type": "string", "enum": ["VA", "BVA", "NVA"]},
        "complexity_score": {"type": "string", "enum": ["low", "medium", "high"]},
        "automation_potential": {"type": "string", "enum": ["high", "medium", "low", "none"]},
        "estimated_duration": {"type": "string", "enum": ["minutes", "hours", "days"]},
        "estimated_frequency": {"type": "string", "enum": ["per_transaction", "daily", "weekly", "monthly"]},
        "confidence": {"type": "number"},
        "needs_review": {"type": "boolean"},
        "sequencing": {
            "type": "object",
            "properties": {
                "position": {"type": "integer"},
                "parallel_group": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
    },
    "required": [
        "name", "level", "description", "evidence_refs",
        "actors", "trigger_conditions", "system_touchpoints",
        "value_classification", "automation_potential", "complexity_score",
        "confidence", "needs_review",
    ],
    "additionalProperties": False,
}

DISCOVERY_V2_DOMAIN_SCHEMA: dict = {
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
                    "key_objects": {"type": "array", "items": {"type": "string"}},
                    "key_terms": {"type": "array", "items": {"type": "string"}},
                    "reasoning": {"type": "string"},
                },
                "required": ["name", "description", "confidence", "key_objects", "key_terms", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["domains"],
    "additionalProperties": False,
}

DISCOVERY_V2_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "processes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "level": {"type": "string", "enum": ["process"]},
                    "description": {"type": "string"},
                    "narrative": {"type": "string"},
                    "evidence_refs": _EVIDENCE_REF_ARRAY,
                    "confidence": {"type": "number"},
                    "needs_review": {"type": "boolean"},
                    "actors": {"type": "array", "items": _V2_ACTOR},
                    "trigger_conditions": {"type": "array", "items": _V2_TRIGGER},
                    "system_touchpoints": {"type": "array", "items": _V2_TOUCHPOINT},
                    "decision_logic": {"type": "array", "items": _V2_DECISION},
                    "success_criteria": {"type": "array", "items": _V2_SUCCESS},
                    "failure_modes": {"type": "array", "items": _V2_FAILURE},
                    "value_classification": {"type": "string", "enum": ["VA", "BVA", "NVA"]},
                    "complexity_score": {"type": "string", "enum": ["low", "medium", "high"]},
                    "automation_potential": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "children": {"type": "array", "items": _V2_CHILD},
                },
                "required": [
                    "name", "description", "evidence_refs", "confidence",
                    "actors", "trigger_conditions", "system_touchpoints",
                    "value_classification", "automation_potential", "children",
                ],
                "additionalProperties": False,
            },
        },
        "intra_domain_handoffs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string", "enum": ["integration", "manual", "automated", "unknown"]},
                    "description": {"type": "string"},
                    "evidence_refs": _EVIDENCE_REF_ARRAY,
                    "confidence": {"type": "number"},
                },
                "required": ["source", "target", "type"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["processes"],
    "additionalProperties": False,
}

DISCOVERY_V2_VERIFICATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "verifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "process_name": {"type": "string"},
                    "claim": {"type": "string"},
                    "evidence_ref": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["CONFIRMED", "WEAK", "UNSUPPORTED"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["process_name", "claim", "evidence_ref", "verdict", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verifications"],
    "additionalProperties": False,
}

DISCOVERY_V2_SYNTHESIS_SCHEMA: dict = {
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
                    "description": {"type": "string"},
                    "evidence_refs": _EVIDENCE_REF_ARRAY,
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
                    "type": {"type": "string", "enum": ["object", "automation", "component"]},
                    "api_name": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["type", "api_name"],
                "additionalProperties": False,
            },
        },
        "domain_narratives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "narrative": {"type": "string"},
                },
                "required": ["domain", "narrative"],
                "additionalProperties": False,
            },
        },
        "executive_summary": {"type": "string"},
    },
    "required": ["cross_domain_handoffs", "executive_summary"],
    "additionalProperties": False,
}


AGENT_OPPORTUNITY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "agent_opportunities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "agent_type": {
                        "type": "string",
                        "enum": ["headless", "conversational", "hybrid"],
                    },
                    "description": {"type": "string"},
                    "topics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic_name": {"type": "string"},
                                "description": {"type": "string"},
                                "reasoning_type": {
                                    "type": "string",
                                    "enum": ["deterministic", "agentic", "hybrid"],
                                },
                                "actions_needed": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "topic_name",
                                "description",
                                "reasoning_type",
                                "actions_needed",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "replaces": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "process_id": {"type": "string"},
                                "process_name": {"type": "string"},
                                "steps_replaced": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "step_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "replacement_type": {
                                    "type": "string",
                                    "enum": ["full", "partial"],
                                },
                            },
                            "required": [
                                "process_id",
                                "process_name",
                                "steps_replaced",
                                "step_ids",
                                "replacement_type",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "trigger": {"type": "string"},
                    "data_requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "suggested_metadata_refs": {
                        "type": "array",
                        "description": "Optional untrusted Salesforce metadata hints from the LLM. Arcflare validates these separately; they are not deployable dependencies.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ref_type": {
                                    "type": "string",
                                    "enum": ["object", "field", "flow", "apex", "queue", "external_system", "unknown"],
                                },
                                "raw_value": {"type": "string"},
                                "object_api_name": {"type": "string"},
                                "field_api_name": {"type": "string"},
                                "operation": {
                                    "type": "string",
                                    "enum": ["read", "write", "create", "update", "delete", "execute", "unknown"],
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["ref_type", "raw_value", "object_api_name", "field_api_name", "operation", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "integration_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "complexity_estimate": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                    "risks": {"type": "string"},
                    "financial_signals": {
                        "type": "object",
                        "properties": {
                            "actors_impacted": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "estimated_hours_per_week_saved": {
                                "type": "number",
                                "description": "Total human effort saved per week across all actors, not per-person hours.",
                            },
                            "estimated_frequency": {
                                "type": "string",
                                "enum": ["daily", "weekly", "monthly", "ad-hoc"],
                            },
                            "estimated_actor_count": {
                                "type": "number",
                                "description": "Human people currently doing the work; exclude records, customers, licenses, Salesforce Users, automations, objects, flows, Apex classes, and components.",
                            },
                            "primary_role_type": {"type": "string"},
                        },
                        "required": [
                            "actors_impacted",
                            "estimated_hours_per_week_saved",
                            "estimated_frequency",
                            "estimated_actor_count",
                            "primary_role_type",
                        ],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "agent_name",
                    "agent_type",
                    "description",
                    "topics",
                    "replaces",
                    "trigger",
                    "data_requirements",
                    "integration_points",
                    "complexity_estimate",
                    "confidence",
                    "rationale",
                    "risks",
                    "financial_signals",
                ],
                "additionalProperties": False,
            },
        },
        "uncovered_processes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "process_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["process_name", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["agent_opportunities", "uncovered_processes"],
    "additionalProperties": False,
}

AGENT_OPPORTUNITY_CROSS_DOMAIN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "cross_domain_opportunities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "agent_type": {
                        "type": "string",
                        "enum": ["headless", "conversational", "hybrid"],
                    },
                    "description": {"type": "string"},
                    "topics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic_name": {"type": "string"},
                                "description": {"type": "string"},
                                "reasoning_type": {
                                    "type": "string",
                                    "enum": ["deterministic", "agentic", "hybrid"],
                                },
                                "actions_needed": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "topic_name",
                                "description",
                                "reasoning_type",
                                "actions_needed",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "replaces": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "process_id": {"type": "string"},
                                "process_name": {"type": "string"},
                                "steps_replaced": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "step_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "replacement_type": {
                                    "type": "string",
                                    "enum": ["full", "partial"],
                                },
                            },
                            "required": [
                                "process_id",
                                "process_name",
                                "steps_replaced",
                                "step_ids",
                                "replacement_type",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "source_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "trigger": {"type": "string"},
                    "data_requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "suggested_metadata_refs": {
                        "type": "array",
                        "description": "Optional untrusted Salesforce metadata hints from the LLM. Arcflare validates these separately; they are not deployable dependencies.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ref_type": {
                                    "type": "string",
                                    "enum": ["object", "field", "flow", "apex", "queue", "external_system", "unknown"],
                                },
                                "raw_value": {"type": "string"},
                                "object_api_name": {"type": "string"},
                                "field_api_name": {"type": "string"},
                                "operation": {
                                    "type": "string",
                                    "enum": ["read", "write", "create", "update", "delete", "execute", "unknown"],
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["ref_type", "raw_value", "object_api_name", "field_api_name", "operation", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "integration_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "complexity_estimate": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                    "risks": {"type": "string"},
                    "financial_signals": {
                        "type": "object",
                        "properties": {
                            "actors_impacted": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "estimated_hours_per_week_saved": {
                                "type": "number",
                                "description": "Total human effort saved per week across all actors, not per-person hours.",
                            },
                            "estimated_frequency": {"type": "string"},
                            "estimated_actor_count": {
                                "type": "number",
                                "description": "Human people currently doing the work; exclude records, customers, licenses, Salesforce Users, automations, objects, flows, Apex classes, and components.",
                            },
                            "primary_role_type": {"type": "string"},
                        },
                        "required": [
                            "actors_impacted",
                            "estimated_hours_per_week_saved",
                            "estimated_frequency",
                            "estimated_actor_count",
                            "primary_role_type",
                        ],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "agent_name",
                    "agent_type",
                    "description",
                    "topics",
                    "replaces",
                    "source_domains",
                    "trigger",
                    "data_requirements",
                    "integration_points",
                    "complexity_estimate",
                    "confidence",
                    "rationale",
                    "risks",
                    "financial_signals",
                ],
                "additionalProperties": False,
            },
        },
        "merge_suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_a": {"type": "string"},
                    "agent_b": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["agent_a", "agent_b", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cross_domain_opportunities", "merge_suggestions"],
    "additionalProperties": False,
}


AGENT_DESIGN_PACKAGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "agent": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["headless", "conversational", "hybrid"]},
                "summary": {"type": "string"},
                "trigger": {"type": "string"},
            },
            "required": ["name", "type", "summary", "trigger"],
            "additionalProperties": False,
        },
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "reasoning_type": {"type": "string"},
                    "actions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "description", "reasoning_type", "actions"],
                "additionalProperties": False,
            },
        },
        "session_variables": {"type": "array", "items": {"type": "object"}},
        "action_contracts": {"type": "array", "items": {"type": "object"}},
        "permission_requirements": {"type": "array", "items": {"type": "object"}},
        "test_scenarios": {"type": "array", "items": {"type": "object"}},
        "observability": {"type": "object"},
        "integration_requirements": {"type": "array", "items": {"type": "object"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "agent",
        "topics",
        "session_variables",
        "action_contracts",
        "permission_requirements",
        "test_scenarios",
        "observability",
        "integration_requirements",
        "blockers",
        "warnings",
    ],
    "additionalProperties": True,
}


OPERATION_SCHEMAS: dict[str, dict] = {
    "discovery_domain": DISCOVERY_DOMAIN_SCHEMA,
    "discovery_structure": DISCOVERY_STRUCTURE_SCHEMA,
    "discovery_enrichment": DISCOVERY_ENRICHMENT_SCHEMA,
    "discovery_flow": DISCOVERY_FLOW_SCHEMA,
    "discovery_enrichment_flow": DISCOVERY_ENRICHMENT_FLOW_SCHEMA,
    "discovery_validation": DISCOVERY_VALIDATION_SCHEMA,
    "discovery_synthesis": DISCOVERY_SYNTHESIS_SCHEMA,
    "discovery_v2_domain": DISCOVERY_V2_DOMAIN_SCHEMA,
    "discovery_v2_extraction": DISCOVERY_V2_EXTRACTION_SCHEMA,
    "discovery_v2_verification": DISCOVERY_V2_VERIFICATION_SCHEMA,
    "discovery_v2_synthesis": DISCOVERY_V2_SYNTHESIS_SCHEMA,
    "agent_opportunity": AGENT_OPPORTUNITY_SCHEMA,
    "agent_opportunity_cross_domain": AGENT_OPPORTUNITY_CROSS_DOMAIN_SCHEMA,
    "agent_design_package": AGENT_DESIGN_PACKAGE_SCHEMA,
}


def get_response_schema(operation: str | None) -> dict | None:
    """Return the JSON Schema for an operation, or None if unschemaed."""
    if not operation:
        return None
    return OPERATION_SCHEMAS.get(operation)
