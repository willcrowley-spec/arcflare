"""Named LLM operations with default tier mappings.

Single source of truth for what pipeline operations exist,
which tier they default to, and their UI-facing metadata.
"""
from __future__ import annotations

from typing import Literal

TierName = Literal["lite", "fast", "strong"]

MODEL_OPERATIONS: dict[str, dict] = {
    "metadata_enrichment": {
        "tier": "lite",
        "thinking_budget": 0,
        "label": "Metadata Enrichment",
        "group": "metadata",
        "description": "Generates business-context descriptions for platform objects with few fields/records. Uses the cheapest model for bulk throughput.",
    },
    "entity_extraction": {
        "tier": "fast",
        "thinking_budget": 0,
        "label": "Entity Extraction",
        "group": "metadata",
        "description": "Extracts business entities (processes, metrics, teams) from document text when rule-based NER falls short.",
    },
    "process_matching": {
        "tier": "fast",
        "thinking_budget": 0,
        "label": "Process Matching",
        "group": "analysis",
        "description": "Disambiguates fuzzy entity matches across documents and data sources.",
    },
    "discovery_domain": {
        "tier": "strong",
        "thinking_budget": 8192,
        "label": "Domain Identification",
        "group": "discovery",
        "description": "Pass 1 of process discovery: identifies top-level business domains from metadata, documents, and org context.",
    },
    "discovery_decomposition": {
        "tier": "strong",
        "thinking_budget": 8192,
        "label": "Process Decomposition",
        "group": "discovery",
        "description": "Pass 2: decomposes each domain into hierarchical sub-processes, steps, and handoffs.",
    },
    "discovery_synthesis": {
        "tier": "strong",
        "thinking_budget": 8192,
        "label": "Cross-Domain Synthesis",
        "group": "discovery",
        "description": "Pass 3: identifies cross-domain handoffs, gaps, and orphaned artifacts across the full process landscape.",
    },
    "recommendations": {
        "tier": "strong",
        "thinking_budget": 10000,
        "label": "Recommendations",
        "group": "synthesis",
        "description": "Generates business process documents and improvement recommendations from clustered entities.",
    },
    "embedding": {
        "tier": "lite",
        "thinking_budget": 0,
        "label": "Embeddings",
        "group": "metadata",
        "description": "Vector embeddings for RAG search across metadata, documents, and org context. Uses a dedicated embedding model.",
    },
}

OPERATION_GROUPS: dict[str, str] = {
    "metadata": "Metadata Pipeline",
    "analysis": "Analysis",
    "discovery": "Discovery Pipeline",
    "synthesis": "Synthesis",
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


def resolve_model_for_operation(
    operation: str | None,
    model_config: dict | None,
    tier: TierName,
) -> tuple[str, str] | None:
    """Check org-level model_config for an operation override.

    Returns (provider, model) if an override exists, else None
    so the caller falls through to env-var / hardcoded defaults.
    """
    if not model_config or not operation:
        return None
    overrides = model_config.get("model_overrides")
    if not overrides or not isinstance(overrides, dict):
        return None
    override = overrides.get(operation)
    if not override or not isinstance(override, str) or "/" not in override:
        return None
    provider, model = override.split("/", 1)
    return provider.strip(), model.strip()
