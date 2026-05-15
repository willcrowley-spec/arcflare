"""Named LLM operations with default tier mappings and model routing.

Single source of truth for what pipeline operations exist, which model
they default to, and their UI-facing metadata.  Model strings use LiteLLM
``provider/model`` format for automatic provider dispatch.
"""
from __future__ import annotations

from typing import Literal

TierName = Literal["lite", "fast", "strong"]

MODEL_OPERATIONS: dict[str, dict] = {
    "metadata_enrichment": {
        "model": "gemini/gemini-3.1-flash-lite-preview",
        "tier": "lite",
        "thinking_budget": 0,
        "output_format": "text",
        "label": "Metadata Enrichment",
        "group": "metadata",
        "description": "Generates business-context descriptions for platform objects with few fields/records. Uses the cheapest model for bulk throughput.",
    },
    "community_summarization": {
        "model": "gemini/gemini-3.1-flash-lite-preview",
        "tier": "lite",
        "thinking_budget": 0,
        "output_format": "text",
        "label": "Community Summarization",
        "group": "metadata",
        "description": "Generates level-appropriate summaries for metadata and document community clusters (GraphRAG retrieval anchors).",
    },
    "contextual_retrieval": {
        "model": "gemini/gemini-3.1-flash-lite-preview",
        "tier": "lite",
        "thinking_budget": 0,
        "output_format": "text",
        "label": "Contextual Retrieval",
        "group": "metadata",
        "description": "Generates 1-2 sentence context prefixes for document chunks before embedding (Anthropic Contextual Retrieval technique).",
    },
    "entity_extraction": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Entity Extraction",
        "group": "metadata",
        "description": "Extracts business entities (processes, metrics, teams) from document text when rule-based NER falls short.",
    },
    "process_matching": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Process Matching",
        "group": "analysis",
        "description": "Disambiguates fuzzy entity matches across documents and data sources.",
    },
    "discovery_domain": {
        "model": "anthropic/claude-opus-4-6",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "Domain Discovery",
        "group": "discovery",
        "description": "Stage 1: identifies top-level business domains from metadata, documents, and org context.",
    },
    "discovery_structure": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Structural Decomposition",
        "group": "discovery",
        "description": "Stage 2: decomposes each domain into hierarchical processes, subprocesses, and steps.",
    },
    "discovery_enrichment": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Step Enrichment",
        "group": "discovery",
        "description": "Stage 3: enriches each step with triggers, decision logic, system touchpoints, and value classification.",
    },
    "discovery_flow": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Flow & Handoff Analysis",
        "group": "discovery",
        "description": "Stage 4: identifies step-to-step flows, parallel groups, and within-domain handoffs.",
    },
    "discovery_enrichment_flow": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Enrichment + Flow (Merged)",
        "group": "discovery",
        "description": "Stage 3+4 merged: enriches steps with operational details and identifies flows/handoffs in a single pass.",
    },
    "discovery_validation": {
        "model": "anthropic/claude-opus-4-6",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "Validation & Refinement",
        "group": "discovery",
        "description": "Stage 5: critiques the complete process map against raw evidence and patches issues.",
    },
    "discovery_synthesis": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Cross-Domain Synthesis",
        "group": "discovery",
        "description": "Stage 6: identifies cross-domain handoffs, gaps, and orphaned artifacts across the full process landscape.",
    },
    "discovery_v2_domain": {
        "model": "anthropic/claude-opus-4-6",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "v2 Domain Discovery",
        "group": "discovery",
        "description": "v2 Phase 1: identifies business domains with key_objects and key_terms for evidence retrieval.",
    },
    "discovery_v2_extraction": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "v2 Per-Domain Extraction",
        "group": "discovery",
        "description": "v2 Phase 3: extracts full process hierarchy per domain from an evidence bundle with mandatory citation.",
    },
    "discovery_v2_verification": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "v2 Evidence Verification",
        "group": "discovery",
        "description": "v2 Phase 4: independently verifies each evidence citation against source data.",
    },
    "discovery_v2_synthesis": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "v2 Cross-Domain Synthesis",
        "group": "discovery",
        "description": "v2 Phase 5: identifies cross-domain handoffs and gaps from verified process trees.",
    },
    "recommendations": {
        "model": "cerebras/gpt-oss-120b",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "text",
        "label": "Recommendation Scoring",
        "group": "synthesis",
        "description": "LLM scoring pass: generates automation narratives, financial assumptions, and executive summaries for each recommendation candidate.",
    },
    "recommendations_composite": {
        "model": "cerebras/gpt-oss-120b",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "Composite Synthesis",
        "group": "synthesis",
        "description": "Identifies cross-process composite automation opportunities from discovered processes and handoffs.",
    },
    "chat_recommendation": {
        "model": "gemini/gemini-2.5-pro",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Recommendation Chat",
        "group": "chat",
        "description": "Recommendation enrichment chat — helps users evaluate ROI, refine assumptions, and discuss automation approaches.",
    },
    "agent_opportunity": {
        "model": "cerebras/gpt-oss-120b",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "Agent Opportunity Analysis",
        "group": "synthesis",
        "description": "Domain-level analysis identifying Agentforce agent opportunities across processes and steps.",
    },
    "agent_opportunity_cross_domain": {
        "model": "cerebras/gpt-oss-120b",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "Cross-Domain Agent Synthesis",
        "group": "synthesis",
        "description": "Identifies agent opportunities spanning multiple business domains.",
    },
    "agent_design_package": {
        "model": "cerebras/gpt-oss-120b",
        "tier": "strong",
        "thinking_budget": 0,
        "reasoning_effort": "high",
        "output_format": "json",
        "label": "Agent Design Package",
        "group": "synthesis",
        "description": "Produces contract-first Agentforce design packages from accepted recommendations, process evidence, and Salesforce metadata.",
    },
    "org_research_extraction": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Org Research Extraction",
        "group": "research",
        "description": "Extracts categorized business facts from crawled web pages and search results about an organization.",
    },
    "org_research_verification": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Org Research Verification",
        "group": "research",
        "description": "Verifies extracted claims against source text. Binary classification: CONFIRMED, WEAK, or UNSUPPORTED.",
    },
    "org_research_synthesis": {
        "model": "gemini/gemini-2.5-flash",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Org Research Synthesis",
        "group": "research",
        "description": "Synthesizes verified facts into executive narrative, ICP analysis, and financial driver speculation.",
    },
    "embedding": {
        "tier": "lite",
        "thinking_budget": 0,
        "output_format": "none",
        "label": "Embeddings",
        "group": "metadata",
        "description": "Vector embeddings for RAG search across metadata, documents, and org context. Uses a dedicated embedding model.",
    },
    "chat": {
        "model": "gemini/gemini-2.5-pro",
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Chat Assistant",
        "group": "chat",
        "description": "Guided discovery agent (Arc). Returns structured JSON responses for interactive UI rendering.",
    },
    "chat_templates": {
        "tier": "none",
        "thinking_budget": 0,
        "output_format": "none",
        "label": "Chat Templates",
        "group": "chat",
        "description": "User-facing message templates that seed contextual chat conversations (e.g. gap opener).",
    },
}

OPERATION_GROUPS: dict[str, str] = {
    "metadata": "Metadata Pipeline",
    "analysis": "Analysis",
    "discovery": "Discovery Pipeline",
    "research": "Org Research",
    "synthesis": "Synthesis",
    "chat": "Chat Assistant",
}

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "anthropic": {
        "lite": "anthropic/claude-3-haiku-20240307",
        "fast": "anthropic/claude-sonnet-4-6",
        "strong": "anthropic/claude-opus-4-6",
    },
    "openai": {
        "lite": "openai/gpt-4o-mini",
        "fast": "openai/gpt-4o",
        "strong": "openai/gpt-4o",
    },
    "gemini": {
        "lite": "gemini/gemini-3.1-flash-lite-preview",
        "fast": "gemini/gemini-2.5-flash",
        "strong": "gemini/gemini-2.5-pro",
    },
    "cerebras": {
        "lite": "cerebras/llama3.1-8b",
        "fast": "cerebras/gpt-oss-120b",
        "strong": "cerebras/gpt-oss-120b",
    },
}


def get_default_tier(operation: str) -> TierName:
    """Return the default tier for a named operation, falling back to 'fast'."""
    entry = MODEL_OPERATIONS.get(operation)
    if entry:
        return entry["tier"]
    return "fast"


def get_thinking_budget(operation: str | None) -> int:
    """Return the thinking token budget for a named operation (0 = no thinking)."""
    if not operation:
        return 0
    entry = MODEL_OPERATIONS.get(operation)
    if entry:
        return int(entry.get("thinking_budget", 0))
    return 0


def get_reasoning_effort(operation: str | None) -> str | None:
    """Return the reasoning_effort level for a named operation, or None."""
    if not operation:
        return None
    entry = MODEL_OPERATIONS.get(operation)
    if entry:
        return entry.get("reasoning_effort")
    return None


def get_output_format(operation: str | None) -> str:
    """Return the output format for a named operation: 'json', 'text', or 'none'."""
    if not operation:
        return "text"
    entry = MODEL_OPERATIONS.get(operation)
    if entry:
        return str(entry.get("output_format", "text"))
    return "text"


def resolve_model(
    operation: str | None = None,
    model_config: dict | None = None,
    tier: TierName = "fast",
) -> str:
    """Resolve a LiteLLM model string via: org override -> op default -> tier default.

    Returns a ``provider/model`` string that LiteLLM dispatches automatically.
    """
    if model_config and operation:
        overrides = model_config.get("model_overrides")
        if isinstance(overrides, dict):
            override = overrides.get(operation)
            if override and isinstance(override, str):
                return override.strip()

    if operation:
        op = MODEL_OPERATIONS.get(operation, {})
        if op.get("model"):
            return op["model"]

    defaults = PROVIDER_DEFAULTS.get("anthropic", {})
    return defaults.get(tier, "anthropic/claude-sonnet-4-6")
