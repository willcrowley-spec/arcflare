"""Tool registry for the AI chat assistant (names align with ChatAction.action_type).

Base tools apply to every thread. Entries from ``recommendation_tools.RECOMMENDATION_TOOLS`` are
merged when the thread's ``anchor_type`` is ``recommendation`` so the model only sees enrichment
tools in that context.
"""

from __future__ import annotations

from app.services.chat.tools.recommendation_tools import RECOMMENDATION_TOOLS
from app.services.chat.tools.registry import BASE_TOOL_REGISTRY

# Backward compatibility: historically this was the full static list (base only now).
TOOL_REGISTRY: list[dict] = BASE_TOOL_REGISTRY


def tools_for_anchor(anchor_type: str | None) -> list[dict]:
    if anchor_type == "recommendation":
        return BASE_TOOL_REGISTRY + RECOMMENDATION_TOOLS
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
