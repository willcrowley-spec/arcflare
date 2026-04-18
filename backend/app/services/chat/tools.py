"""Tool registry for the AI chat assistant (names align with ChatAction.action_type)."""

from __future__ import annotations

TOOL_REGISTRY: list[dict] = [
    {
        "name": "search_knowledge",
        "description": (
            "Runs semantic search over the organization's uploaded documents and knowledge chunks "
            "stored in the vector index. Use it when the user asks factual questions about internal "
            "policies, procedures, or document content that may not be in the process graph. "
            "Do not use it when the question is purely about navigating or editing BusinessProcess "
            "records, handoffs, or gap metadata—use process and handoff tools instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query aligned with what to find in docs.",
                },
            },
            "required": ["query"],
        },
        "auto_execute": True,
        "risk_level": "none",
    },
    {
        "name": "get_process_detail",
        "description": (
            "Loads a single BusinessProcess by ID together with its child processes and related "
            "handoffs for read-only inspection. Use it when the user references a specific process "
            "or needs structure, narrative, actors, or automation context. "
            "Do not use it for broad portfolio questions where listing or KPIs across many processes "
            "is required without a known ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the BusinessProcess in the current organization.",
                },
            },
            "required": ["process_id"],
        },
        "auto_execute": True,
        "risk_level": "none",
    },
    {
        "name": "list_gaps",
        "description": (
            "Returns all cross-domain ProcessHandoff rows flagged as gaps for the organization, "
            "including metadata useful for triage. Use it when the user wants an inventory of "
            "integration gaps, unresolved boundaries, or discovery findings. "
            "Do not use it when the user already provided a specific handoff ID or only needs "
            "non-gap handoffs."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
        "auto_execute": True,
        "risk_level": "none",
    },
    {
        "name": "create_process",
        "description": (
            "Creates a new BusinessProcess under the organization, optionally nested under a parent. "
            "Use it when the user explicitly wants to add a domain, process, subprocess, or step "
            "that should appear in the catalog and graphs. "
            "Do not use it for speculative modeling without confirmation, or when the user is only "
            "explaining existing work—prefer read-only tools first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name of the new process."},
                "description": {"type": "string", "description": "Optional longer description."},
                "category": {"type": "string", "description": "Optional category label."},
                "parent_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Optional parent BusinessProcess UUID.",
                },
                "level": {
                    "type": "string",
                    "enum": ["domain", "process", "subprocess", "step"],
                    "description": "Hierarchy level for the new row.",
                },
                "actors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Participating actors or roles.",
                },
                "artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Systems, documents, or artifacts touched.",
                },
            },
            "required": ["name"],
        },
        "auto_execute": False,
        "risk_level": "medium",
    },
    {
        "name": "update_process",
        "description": (
            "Patches fields on an existing BusinessProcess such as name, narrative, status, or scores. "
            "Use it when the user wants to correct or enrich a known process record after review. "
            "Do not use it to delete data, to change IDs, or when the target process has not been "
            "identified and scoped to this organization."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "process_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string"},
                "category": {"type": "string"},
                "confidence_score": {"type": "number"},
                "narrative": {"type": "string"},
                "actors": {"type": "array", "items": {"type": "string"}},
                "artifacts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["process_id"],
        },
        "auto_execute": False,
        "risk_level": "medium",
    },
    {
        "name": "delete_process",
        "description": (
            "Soft-deletes a BusinessProcess and its descendant processes by marking status deleted, "
            "preserving audit history while hiding the subtree from active views. "
            "Use only after explicit user confirmation of destructive intent. "
            "Do not use it for routine cleanup of handoffs alone, for merging duplicates without "
            "review, or when children or cross-domain handoffs have not been considered."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "process_id": {"type": "string", "format": "uuid"},
            },
            "required": ["process_id"],
        },
        "auto_execute": False,
        "risk_level": "high",
    },
    {
        "name": "create_handoff",
        "description": (
            "Creates a ProcessHandoff linking a source process to a target process with a typed "
            "relationship. Use it when modeling integrations, manual bridges, or data flows between "
            "known processes. "
            "Do not use it if either endpoint process is unknown, belongs to another org, or when "
            "the user has not confirmed the direction and handoff semantics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source_process_id": {"type": "string", "format": "uuid"},
                "target_process_id": {"type": "string", "format": "uuid"},
                "handoff_type": {
                    "type": "string",
                    "enum": [
                        "integration",
                        "manual",
                        "automated",
                        "approval_handoff",
                        "data_handoff",
                        "unknown",
                    ],
                },
                "description": {"type": "string"},
            },
            "required": ["source_process_id", "target_process_id", "handoff_type"],
        },
        "auto_execute": False,
        "risk_level": "medium",
    },
    {
        "name": "update_handoff",
        "description": (
            "Updates metadata on an existing ProcessHandoff such as type, description, or confidence. "
            "Use it for refinements after human review or when correcting extraction mistakes. "
            "Do not use it to change org ownership, to toggle gap resolution—use resolve_gap—or when "
            "the handoff ID is uncertain."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "handoff_id": {"type": "string", "format": "uuid"},
                "handoff_type": {
                    "type": "string",
                    "enum": [
                        "integration",
                        "manual",
                        "automated",
                        "approval_handoff",
                        "data_handoff",
                        "unknown",
                    ],
                },
                "description": {"type": "string"},
                "confidence_score": {"type": "number"},
            },
            "required": ["handoff_id"],
        },
        "auto_execute": False,
        "risk_level": "low",
    },
    {
        "name": "resolve_gap",
        "description": (
            "Marks a gap handoff as resolved and stores an auditable resolution note for compliance. "
            "Use it when the user confirms that integration work, documentation, or ownership fixes "
            "addressed the gap. "
            "Do not use it without a substantive resolution_note, or when the row is not flagged as "
            "a gap—prefer update_handoff for generic edits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "handoff_id": {"type": "string", "format": "uuid"},
                "resolution_note": {"type": "string", "description": "Why and how the gap was closed."},
            },
            "required": ["handoff_id", "resolution_note"],
        },
        "auto_execute": False,
        "risk_level": "low",
    },
    {
        "name": "rerun_synthesis",
        "description": (
            "Queues the discovery pipeline's synthesis phase (Pass 3 aggregate) to refresh models "
            "from the latest ingested evidence. Use when stakeholders explicitly request a full "
            "rebuild after major document or connection changes. "
            "Do not use it while another discovery run is already executing for the org, or for "
            "small single-process edits that should use update_process instead."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
        "auto_execute": False,
        "risk_level": "medium",
    },
]

_TOOL_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOOL_REGISTRY}


def get_tool(name: str) -> dict | None:
    return _TOOL_BY_NAME.get(name)


def get_tool_declarations() -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in TOOL_REGISTRY
    ]


def get_openai_tools() -> list[dict]:
    """Return tool definitions in OpenAI function-calling format.

    This is the industry-standard format that LiteLLM accepts and
    translates to provider-native format automatically.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOL_REGISTRY
    ]
