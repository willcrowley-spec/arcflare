"""Registry of prompt block definitions per operation."""

from __future__ import annotations

BLOCK_REGISTRY: dict[str, list[dict]] = {
    "chat": [
        {
            "type": "identity",
            "label": "Identity",
            "editable": True,
            "required_vars": ["agent_name"],
            "order": 1,
        },
        {
            "type": "rules",
            "label": "Rules",
            "editable": True,
            "required_vars": [],
            "order": 2,
        },
        {
            "type": "protocol",
            "label": "Protocol",
            "editable": False,
            "required_vars": [],
            "order": 3,
        },
        {
            "type": "workflow",
            "label": "Workflow",
            "editable": True,
            "required_vars": [],
            "order": 4,
        },
        {
            "type": "examples",
            "label": "Examples",
            "editable": True,
            "required_vars": ["agent_name"],
            "order": 5,
        },
    ],
    "discovery_domain": [
        {
            "type": "instructions",
            "label": "Instructions",
            "editable": True,
            "required_vars": [],
            "order": 1,
        },
        {
            "type": "protocol",
            "label": "Protocol",
            "editable": False,
            "required_vars": [],
            "order": 2,
        },
    ],
    "discovery_structure": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_enrichment": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_flow": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_validation": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_synthesis": [
        {
            "type": "instructions",
            "label": "Instructions",
            "editable": True,
            "required_vars": [],
            "order": 1,
        },
        {
            "type": "protocol",
            "label": "Protocol",
            "editable": False,
            "required_vars": [],
            "order": 2,
        },
    ],
    "metadata_enrichment": [
        {
            "type": "instructions",
            "label": "Instructions",
            "editable": True,
            "required_vars": [],
            "order": 1,
        },
        {
            "type": "protocol",
            "label": "Protocol",
            "editable": False,
            "required_vars": [],
            "order": 2,
        },
    ],
    "entity_extraction": [
        {
            "type": "instructions",
            "label": "Instructions",
            "editable": True,
            "required_vars": [],
            "order": 1,
        },
        {
            "type": "instructions_batch",
            "label": "Batch instructions",
            "editable": True,
            "required_vars": [],
            "order": 2,
        },
        {
            "type": "protocol",
            "label": "Protocol",
            "editable": False,
            "required_vars": [],
            "order": 3,
        },
    ],
    "recommendations": [
        {
            "type": "instructions",
            "label": "Instructions",
            "editable": True,
            "required_vars": [],
            "order": 1,
        },
        {
            "type": "protocol",
            "label": "Protocol",
            "editable": False,
            "required_vars": [],
            "order": 2,
        },
        {
            "type": "examples",
            "label": "Examples",
            "editable": True,
            "required_vars": [],
            "order": 3,
        },
    ],
    "recommendations_composite": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "chat_recommendation": [
        {"type": "identity", "label": "Identity", "editable": True, "required_vars": ["agent_name"], "order": 1},
        {"type": "rules", "label": "Rules", "editable": True, "required_vars": [], "order": 2},
        {"type": "persona", "label": "Enrichment Persona", "editable": True, "required_vars": [], "order": 3},
    ],
    "discovery_enrichment_flow": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_v2_domain": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_v2_extraction": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_v2_verification": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_v2_synthesis": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "org_research_extraction": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "org_research_verification": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "org_research_synthesis": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Protocol", "editable": False, "required_vars": [], "order": 2},
    ],
    "community_summarization": [
        {"type": "meta_l0", "label": "Metadata L0 (Cluster)", "editable": True, "required_vars": ["members_text"], "order": 1},
        {"type": "meta_l1", "label": "Metadata L1 (Capability)", "editable": True, "required_vars": ["child_summaries"], "order": 2},
        {"type": "meta_l2", "label": "Metadata L2 (Domain)", "editable": True, "required_vars": ["child_summaries"], "order": 3},
        {"type": "doc_summary", "label": "Document Summary", "editable": True, "required_vars": ["concepts", "excerpts_section"], "order": 4},
        {"type": "doc_l1", "label": "Document L1", "editable": True, "required_vars": ["child_summaries"], "order": 5},
    ],
    "contextual_retrieval": [
        {"type": "instructions", "label": "Instructions", "editable": True, "required_vars": ["document_text", "chunk_list"], "order": 1},
    ],
    "chat_templates": [
        {
            "type": "gap_opener",
            "label": "Gap Opener",
            "editable": True,
            "required_vars": [
                "source_process",
                "source_domain",
                "target_process",
                "target_domain",
                "confidence",
            ],
            "order": 1,
        },
    ],
}


def get_registry_for_operation(operation_id: str) -> list[dict] | None:
    blocks = BLOCK_REGISTRY.get(operation_id)
    if blocks is None:
        return None
    return sorted(blocks, key=lambda b: b["order"])


def get_block_meta(operation_id: str, block_type: str) -> dict | None:
    for block in BLOCK_REGISTRY.get(operation_id, []):
        if block["type"] == block_type:
            return block
    return None


def is_block_editable(operation_id: str, block_type: str) -> bool:
    meta = get_block_meta(operation_id, block_type)
    return bool(meta["editable"]) if meta else False


def get_required_vars(operation_id: str, block_type: str) -> list[str]:
    meta = get_block_meta(operation_id, block_type)
    if meta is None:
        return []
    return list(meta["required_vars"])
