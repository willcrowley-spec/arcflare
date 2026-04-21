"""Tool registry for the AI chat assistant (names align with ChatAction.action_type).

Base tools apply to discovery threads. When ``anchor_type`` is ``recommendation``, only a whitelist
of read tools plus ``update_assumption`` is exposed (no process/handoff/gap mutations).
"""

from __future__ import annotations

from app.services.chat.tools.recommendation_tools import RECOMMENDATION_TOOLS
from app.services.chat.tools.registry import BASE_TOOL_REGISTRY

# Backward compatibility: historically this was the full static list (base only now).
TOOL_REGISTRY: list[dict] = BASE_TOOL_REGISTRY

# Recommendation-anchored chat: read-only + assumption updates only (no discovery graph mutations).
_RECOMMENDATION_ANCHOR_TOOL_ORDER: tuple[str, ...] = (
    "get_recommendation_details",
    "get_scoring_breakdown",
    "update_assumption",
    "search_knowledge",
    "get_process_detail",
)


def tools_for_anchor(anchor_type: str | None) -> list[dict]:
    if anchor_type == "recommendation":
        by_name = {t["name"]: t for t in BASE_TOOL_REGISTRY}
        by_name.update({t["name"]: t for t in RECOMMENDATION_TOOLS})
        return [by_name[name] for name in _RECOMMENDATION_ANCHOR_TOOL_ORDER if name in by_name]
    return BASE_TOOL_REGISTRY


def get_tool(name: str, anchor_type: str | None = None) -> dict | None:
    for t in tools_for_anchor(anchor_type):
        if t["name"] == name:
            return t
    return None


def get_tool_declarations(anchor_type: str | None = None) -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in tools_for_anchor(anchor_type)
    ]


def get_openai_tools(anchor_type: str | None = None) -> list[dict]:
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
        for t in tools_for_anchor(anchor_type)
    ]


__all__ = [
    "BASE_TOOL_REGISTRY",
    "RECOMMENDATION_TOOLS",
    "TOOL_REGISTRY",
    "get_openai_tools",
    "get_tool",
    "get_tool_declarations",
    "tools_for_anchor",
]
