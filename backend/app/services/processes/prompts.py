"""Prompt templates for the three-pass process discovery pipeline."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)

_FALLBACK_PASS1_INSTRUCTIONS = """You are a senior business process analyst. Given the following information about an organization and its technology systems, identify the top-level business process domains.

## Instructions
Identify the top-level business process domains present in this organization. For each domain:
- Name it clearly (e.g., "Sales Operations", "Claims Processing", "Customer Onboarding")
- Describe what it encompasses
- List which metadata objects and automations you associate with it
- List which uploaded documents relate to it (by filename)
- Rate your confidence from 0.0 to 1.0
- Explain your reasoning briefly

Do NOT use generic templates. Derive domains from what you actually see in the data.
Objects with zero records or classified as "deprecated" have been excluded."""

_FALLBACK_PASS1_PROTOCOL = """Respond with valid JSON only:
{
  "domains": [
    {
      "name": "string",
      "description": "string",
      "confidence": 0.0,
      "associated_objects": ["ObjectName"],
      "associated_automations": ["AutomationName"],
      "associated_documents": ["filename"],
      "reasoning": "string"
    }
  ]
}"""

_FALLBACK_PASS2_INSTRUCTIONS = """You are a senior business process analyst. You previously identified the following business domain:

## Instructions
Decompose this domain into processes, subprocesses, and steps. For each:
- Name and describe it
- Assign a level: "process", "subprocess", or "step"
- List actors (users, integrations, systems involved)
- List artifacts (specific objects, flows, validation rules that participate)
- Rate your confidence (0.0-1.0)
- Flag needs_review=true if the data is ambiguous
- Write a narrative description of how this process works
- Identify handoffs between processes within this domain"""

_FALLBACK_PASS2_PROTOCOL = """Respond with valid JSON only:
{
  "processes": [
    {
      "name": "string",
      "level": "process|subprocess|step",
      "description": "string",
      "narrative": "string",
      "confidence": 0.0,
      "needs_review": false,
      "actors": [{"name": "string", "type": "user|integration|system"}],
      "artifacts": [{"type": "object|flow|validation_rule|component", "api_name": "string"}],
      "children": []
    }
  ],
  "handoffs": [
    {
      "source": "process name",
      "target": "process name",
      "type": "integration|manual|automated|unknown",
      "description": "string",
      "confidence": 0.0
    }
  ]
}"""

_FALLBACK_PASS3_INSTRUCTIONS = """You are a senior business process analyst. You have mapped the following business process domains:

## Instructions
1. Identify cross-domain handoffs. Where does one domain's output become another domain's input?
2. Flag gaps — places where processes SHOULD connect but there is no evidence of a connection (no integration, no automation, no documented handoff).
3. Categorize orphaned artifacts — do they belong to an undiscovered process?
4. Write an executive summary of how this business operates end-to-end."""

_FALLBACK_PASS3_PROTOCOL = """Respond with valid JSON only:
{
  "cross_domain_handoffs": [
    {
      "source_domain": "string",
      "source_process": "string",
      "target_domain": "string",
      "target_process": "string",
      "type": "integration|manual|automated|unknown",
      "is_gap": true,
      "confidence": 0.0,
      "reasoning": "string"
    }
  ],
  "orphaned_artifacts": [
    {"type": "object|automation", "api_name": "string", "reasoning": "string"}
  ],
  "executive_summary": "string"
}"""


def _pass1_dynamic_sections(
    org_context: dict, metadata_summary: dict, document_summary: list[dict],
) -> str:
    totals = metadata_summary["totals"]
    return f"""## Organization Context
{json.dumps(org_context, indent=2)}

## Platform Metadata Summary
Objects with data: {totals['objects_with_data']}
Automations: {totals['automations']}
Components: {totals['components']}

### Data Objects (sorted by record volume)
{json.dumps(metadata_summary['objects'][:80], indent=2)}

### Automations
{json.dumps(metadata_summary['automations'][:80], indent=2)}

### Components
{json.dumps(metadata_summary['components'][:40], indent=2)}

## Uploaded Documents
{json.dumps(document_summary, indent=2) if document_summary else "No documents uploaded."}"""


def _pass2_dynamic_sections(
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
) -> str:
    excerpts = (
        json.dumps([c["content"][:500] for c in document_chunks[:10]], indent=2)
        if document_chunks
        else "No relevant documents found."
    )
    return f"""## Domain
Name: {domain['name']}
Description: {domain['description']}

## Organization Context
{json.dumps(org_context, indent=2)}

## Detailed Metadata for This Domain
{json.dumps(metadata_detail, indent=2)}

## Relevant Document Excerpts
{excerpts}"""


def _pass3_dynamic_sections(
    org_context: dict, all_domains: list[dict], orphaned_artifacts: list[dict],
) -> str:
    orphaned = (
        json.dumps(orphaned_artifacts[:50], indent=2)
        if orphaned_artifacts
        else "All artifacts are accounted for."
    )
    return f"""## Organization Context
{json.dumps(org_context, indent=2)}

## Discovered Domains and Their Processes
{json.dumps(all_domains, indent=2)}

## Unclaimed Metadata Artifacts
These objects/automations were not associated with any domain:
{orphaned}"""


async def build_pass1_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    metadata_summary: dict,
    document_summary: list[dict],
) -> str:
    blocks = await resolve_prompt_blocks("discovery_domain", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning(
            "discovery_prompt_fallback pass=1 block=instructions org_id=%s",
            org_id,
        )
        instructions = _FALLBACK_PASS1_INSTRUCTIONS
    if not protocol:
        logger.warning(
            "discovery_prompt_fallback pass=1 block=protocol org_id=%s",
            org_id,
        )
        protocol = _FALLBACK_PASS1_PROTOCOL
    middle = _pass1_dynamic_sections(org_context, metadata_summary, document_summary)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


async def build_pass2_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
) -> str:
    blocks = await resolve_prompt_blocks("discovery_structure", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning(
            "discovery_prompt_fallback pass=2 block=instructions org_id=%s",
            org_id,
        )
        instructions = _FALLBACK_PASS2_INSTRUCTIONS
    if not protocol:
        logger.warning(
            "discovery_prompt_fallback pass=2 block=protocol org_id=%s",
            org_id,
        )
        protocol = _FALLBACK_PASS2_PROTOCOL
    middle = _pass2_dynamic_sections(org_context, domain, metadata_detail, document_chunks)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


async def build_pass3_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    all_domains: list[dict],
    orphaned_artifacts: list[dict],
) -> str:
    blocks = await resolve_prompt_blocks("discovery_synthesis", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning(
            "discovery_prompt_fallback pass=3 block=instructions org_id=%s",
            org_id,
        )
        instructions = _FALLBACK_PASS3_INSTRUCTIONS
    if not protocol:
        logger.warning(
            "discovery_prompt_fallback pass=3 block=protocol org_id=%s",
            org_id,
        )
        protocol = _FALLBACK_PASS3_PROTOCOL
    middle = _pass3_dynamic_sections(org_context, all_domains, orphaned_artifacts)
    return f"{instructions}\n\n{middle}\n\n{protocol}"
