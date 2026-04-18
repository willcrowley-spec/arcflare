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
        "label": "Metadata Enrichment",
        "group": "metadata",
        "description": "Generates business-context descriptions for platform objects with few fields/records. Uses the cheapest model for bulk throughput.",
    },
    "entity_extraction": {
        "tier": "fast",
        "label": "Entity Extraction",
        "group": "metadata",
        "description": "Extracts business entities (processes, metrics, teams) from document text when rule-based NER falls short.",
    },
    "process_matching": {
        "tier": "fast",
        "label": "Process Matching",
        "group": "analysis",
        "description": "Disambiguates fuzzy entity matches across documents and data sources.",
    },
    "discovery_domain": {
        "tier": "strong",
        "label": "Domain Identification",
        "group": "discovery",
        "description": "Pass 1 of process discovery: identifies top-level business domains from metadata, documents, and org context.",
    },
    "discovery_decomposition": {
        "tier": "strong",
        "label": "Process Decomposition",
        "group": "discovery",
        "description": "Pass 2: decomposes each domain into hierarchical sub-processes, steps, and handoffs.",
    },
    "discovery_synthesis": {
        "tier": "strong",
        "label": "Cross-Domain Synthesis",
        "group": "discovery",
        "description": "Pass 3: identifies cross-domain handoffs, gaps, and orphaned artifacts across the full process landscape.",
    },
    "recommendations": {
        "tier": "strong",
        "label": "Recommendations",
        "group": "synthesis",
        "description": "Generates business process documents and improvement recommendations from clustered entities.",
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
