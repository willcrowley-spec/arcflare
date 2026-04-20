"""Prompt templates for the process discovery pipeline."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)

_FALLBACK_PASS1_INSTRUCTIONS = """You are a senior business process analyst. Given the following information about an organization and its technology systems, identify the top-level business process domains.

## Reasoning Instructions
Before listing domains, reason step by step:
1. What business capabilities does this organization's metadata reveal?
2. Which objects cluster together by naming convention, shared lookups, or automation chains?
3. Which document sections describe end-to-end workflows?
4. What are the natural boundaries between different business functions?

## Domain Quality Criteria
- Each domain should own 3-30 metadata objects. A domain with 1 object is too narrow. A domain with 50+ objects is too broad — split it.
- Domains must reflect business capabilities (e.g., "Customer Support Operations"), NOT Salesforce product names (e.g., "Service Cloud").
- Do NOT create catch-all domains like "General Administration" or "Miscellaneous".

## Instructions
For each domain:
- Name it clearly (e.g., "Sales Operations", "Claims Processing", "Customer Onboarding")
- Describe what it encompasses
- List which metadata objects and automations you associate with it
- List which uploaded documents relate to it (by filename)
- Rate your confidence from 0.0 to 1.0
- Explain your reasoning briefly

Do NOT use generic templates. Derive domains from what you actually see in the data.
Objects classified as "excluded" (zero records or manually excluded) have been omitted."""

_FALLBACK_PASS1_PROTOCOL = """Return a JSON object matching the enforced schema:
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

_FALLBACK_STAGE2_INSTRUCTIONS = """You are a senior business process analyst performing structural decomposition of a business domain.

## Reasoning Instructions
Before decomposing, reason step by step:
1. Trace object relationships, automation triggers, and document descriptions to identify major workflows.
2. What are the entry points (events that start a workflow)?
3. What are the terminal outcomes (final states or outputs)?
4. Where are the natural boundaries between processes?

## Hierarchy Definitions (BPMN-derived)
- **Process** — a complete business workflow with a clear trigger and outcome (e.g., "Lead Qualification"). Has 2-8 direct children.
- **Subprocess** — a logical grouping within a process (e.g., "Initial Scoring"). Only use when there's meaningful grouping.
- **Step** — an atomic unit of work performed by one actor in one system (e.g., "Update Lead Status to Qualified"). If a step contains "and", split it into two steps.

## Decomposition Rules
- Most domains decompose to 2-3 levels of depth. Do not go deeper than 4 levels unless evidence warrants it.
- A process with >8 direct children should be split into subprocesses.
- Every leaf node must be a "step" — no empty containers.
- Do NOT include actors, triggers, system touchpoints, or enrichment data. Pure structure only.

## Output Format
- Return a FLAT list of ALL items (processes, subprocesses, steps) in a single array.
- Use parent_name to express hierarchy — do NOT nest children objects.
- Items with no parent (top-level processes) should have parent_name: null.
- Order: parents before their children (parent must appear earlier in the list than its children).

For each item, list which metadata artifacts (objects, flows, validation rules) you associate with it."""

_FALLBACK_STAGE2_PROTOCOL = """Return a JSON object matching the enforced schema. Output a FLAT list of ALL items — processes, subprocesses, AND steps — with parent_name to express hierarchy. Do NOT nest children. Every leaf must be level "step".
{
  "processes": [
    {"name": "Lead Management", "level": "process", "parent_name": null, "description": "...", "narrative": "...", "confidence": 0.85, "needs_review": false, "artifacts": [{"type": "object", "api_name": "Lead"}]},
    {"name": "Lead Scoring", "level": "subprocess", "parent_name": "Lead Management", "description": "...", "narrative": "...", "confidence": 0.8, "needs_review": false, "artifacts": []},
    {"name": "Assign Lead Score", "level": "step", "parent_name": "Lead Scoring", "description": "...", "narrative": "...", "confidence": 0.75, "needs_review": true, "artifacts": [{"type": "flow", "api_name": "Lead_Score_Assignment"}]}
  ]
}"""

_FALLBACK_STAGE3_INSTRUCTIONS = """You are a senior business process analyst performing step-level enrichment. For each step provided, determine agent-grade operational details using the metadata and documents provided.

## Reasoning Instructions
For each step, trace backward from its artifacts:
1. What event or state change triggers this step?
2. What data does it read or write (specific Object.Field)?
3. What decisions or rules are applied?
4. What constitutes success or failure?

## Evidence Rules
- For system_touchpoints, reference SPECIFIC Object.Field names from the metadata provided. Do NOT invent field names.
- If you cannot identify specific fields for a step, set system_touchpoints to an empty array and set needs_review to true.
- Do NOT assign value_classification "VA" to internal administrative steps. VA means the step directly produces something the external customer receives or experiences.

## Enrichment Fields Per Step
1. trigger_conditions — what event or state change initiates this step
2. decision_logic — what rules or judgments are applied
3. system_touchpoints — which Object.Field combinations are read/written/created
4. actors — who performs this (user role, integration, automation)
5. success_criteria — what does "done correctly" look like
6. failure_modes — what can go wrong and how is it recovered
7. value_classification — VA (customer-facing value), BVA (business-necessary), NVA (waste/rework)
8. complexity_score — low (single system, rule-based), medium (multi-system or some judgment), high (cross-system, significant judgment)
9. automation_potential — high (fully rule-based, data available), medium (mostly rule-based, some exceptions), low (judgment-heavy), none (inherently human)
10. estimated_duration — minutes, hours, or days per execution
11. estimated_frequency — per_transaction, daily, weekly, or monthly"""

_FALLBACK_STAGE3_PROTOCOL = """Return a JSON object matching the enforced schema:
{
  "enriched_steps": [
    {
      "name": "string (must match the step name exactly)",
      "trigger_conditions": [{"event": "string", "condition": "string", "source_object": "string", "source_field": "string"}],
      "decision_logic": [{"rule": "string", "outcome": "string", "evidence": "string"}],
      "system_touchpoints": [{"object_api_name": "string", "fields": ["string"], "operation": "read|write|create", "automation_name": null}],
      "actors": [{"name": "string", "type": "user|integration|system"}],
      "success_criteria": [{"criterion": "string", "measurable": true}],
      "failure_modes": [{"mode": "string", "impact": "string", "recovery": "string"}],
      "value_classification": "VA|BVA|NVA",
      "complexity_score": "low|medium|high",
      "automation_potential": "high|medium|low|none",
      "estimated_duration": "minutes|hours|days",
      "estimated_frequency": "per_transaction|daily|weekly|monthly",
      "confidence": 0.0,
      "needs_review": false
    }
  ]
}"""

_FALLBACK_STAGE4_INSTRUCTIONS = """You are a senior business process analyst performing flow and handoff analysis. Given an enriched process hierarchy, identify how steps connect to each other and how processes hand off work.

## Reasoning Instructions
Trace the data flow through this domain in two passes:
1. **Evidence-based connections:** Identify step pairs where (a) step A writes to an object that step B reads, (b) an automation triggers after step A and modifies data for step B, (c) a document describes a handoff between them.
2. **Inferred connections:** For steps that logically must be sequential but have no metadata evidence, mark the connection type as "inferred" with confidence < 0.5.

## Parallel Detection
If two steps read from the same trigger but write to different objects with no dependency between them, they may execute in parallel. Group them.

## Handoff Data Contracts
For each handoff between processes, identify what data transfers — list specific Object.Field combinations that cross the boundary."""

_FALLBACK_STAGE4_PROTOCOL = """Return a JSON object matching the enforced schema:
{
  "step_flows": [
    {
      "source_step": "string (exact step name)",
      "target_step": "string (exact step name)",
      "condition": "string or null",
      "evidence": "string",
      "type": "automated|manual|integration|inferred"
    }
  ],
  "parallel_groups": [
    {"group_name": "string", "step_names": ["string"]}
  ],
  "handoffs": [
    {
      "source": "process name",
      "target": "process name",
      "type": "integration|manual|automated|unknown",
      "description": "string",
      "confidence": 0.0,
      "data_transferred": [{"object": "string", "fields": ["string"]}],
      "transfer_mechanism": "string or null"
    }
  ],
  "entry_points": ["step name"],
  "terminal_points": ["step name"]
}"""

_FALLBACK_STAGE5_INSTRUCTIONS = """You are a senior business process analyst performing quality validation on a complete process map. Review the map against the raw metadata evidence and identify issues.

## Critique Categories
1. **orphaned_metadata** — objects or automations with significant usage (>100 records or active) that no step references
2. **phantom_reference** — steps that claim to touch metadata that doesn't exist or has zero records
3. **structural** — processes with >8 direct children, domains with only 1 process, steps that aren't atomic (contain "and")
4. **confidence_inflation** — steps claiming >0.8 confidence with zero specific field-level touchpoints
5. **missing_flow** — sequential steps with no step_flow connection between them
6. **handoff_gap** — processes that logically should connect but have no handoff defined

## Instructions
Part A: Produce a critique listing every issue found with severity (high/medium/low).
Part B: For each issue, produce a specific fix. Output both the critique and the patched data.

One critique, one patch. Do not iterate."""

_FALLBACK_STAGE5_PROTOCOL = """Return a JSON object matching the enforced schema:
{
  "critique": [
    {
      "issue_type": "orphaned_metadata|phantom_reference|structural|confidence_inflation|missing_flow|handoff_gap",
      "severity": "high|medium|low",
      "description": "string",
      "affected_items": ["string"],
      "fix_applied": "string"
    }
  ],
  "patches": {
    "updated_steps": [],
    "added_flows": [],
    "added_handoffs": [],
    "removed_steps": ["step name"],
    "confidence_adjustments": [{"step_name": "string", "old": 0.0, "new": 0.0, "reason": "string"}]
  }
}"""

_FALLBACK_PASS3_INSTRUCTIONS = """You are a senior business process analyst performing cross-domain synthesis. You have the complete enriched process hierarchy with system touchpoints and flow data.

## Reasoning Instructions
1. Look for shared system_touchpoints across domains — if Domain A writes to Object.Field and Domain B reads the same Object.Field, that's a cross-domain handoff.
2. Look for automation chains that span domains.
3. Flag gaps — domains that logically must connect but share zero objects and zero automations.

## Instructions
1. Identify cross-domain handoffs with data contracts (which Object.Fields transfer).
2. Flag gaps where processes SHOULD connect but there is no evidence.
3. Categorize orphaned artifacts — do they belong to an undiscovered process?
4. Write a 3-paragraph executive summary: (1) core revenue flow, (2) supporting operations, (3) identified gaps and automation opportunities."""

_FALLBACK_PASS3_PROTOCOL = """Return a JSON object matching the enforced schema:
{
  "cross_domain_handoffs": [
    {
      "source_domain": "string",
      "source_process": "string",
      "target_domain": "string",
      "target_process": "string",
      "type": "integration|manual|automated|unknown",
      "is_gap": false,
      "confidence": 0.0,
      "reasoning": "string",
      "data_transferred": [{"object": "string", "fields": ["string"]}],
      "transfer_mechanism": "string or null"
    }
  ],
  "orphaned_artifacts": [
    {"type": "object|automation", "api_name": "string", "reasoning": "string"}
  ],
  "executive_summary": "string"
}"""


def _pass1_dynamic_sections(
    org_context: dict,
    metadata_summary: dict,
    document_summary: list[dict],
    document_index: list[dict] | None = None,
) -> str:
    totals = metadata_summary["totals"]
    doc_index_section = ""
    if document_index:
        doc_index_section = f"\n\n## Uploaded Document Index\n{json.dumps(document_index, indent=2)}"
    excerpts = json.dumps(
        [{"content": c.get("content", "")[:500], "section": c.get("section_title", "")} for c in document_summary[:20]],
        indent=2,
    ) if document_summary else "No documents uploaded."
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
{json.dumps(metadata_summary['components'][:40], indent=2)}{doc_index_section}

## Relevant Document Excerpts
{excerpts}"""


def _stage2_dynamic_sections(
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
) -> str:
    excerpts = (
        json.dumps(
            [{"content": c["content"], "section": c.get("section_title", "")} for c in document_chunks[:10]],
            indent=2,
        )
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


def _stage3_dynamic_sections(
    steps: list[dict],
    metadata_per_step: dict[str, dict],
    document_chunks_per_step: dict[str, list[dict]],
) -> str:
    sections = []
    for step in steps:
        name = step["name"]
        meta = json.dumps(metadata_per_step.get(name, {}), indent=2)
        docs = json.dumps(
            [c["content"] for c in document_chunks_per_step.get(name, [])[:5]],
            indent=2,
        )
        sections.append(f"""### Step: "{name}"
Artifacts: {json.dumps(step.get("artifacts", []))}
Relevant metadata:
{meta}
Relevant documents:
{docs}""")
    return "\n\n".join(sections)


def _stage4_dynamic_sections(
    enriched_tree: list[dict],
    metadata_relationships: dict,
    dependency_graph: list[dict] | None = None,
) -> str:
    sections = [
        f"## Enriched Process Hierarchy\n{json.dumps(enriched_tree, indent=2)}",
        f"## Metadata Relationships (lookups, automations)\n{json.dumps(metadata_relationships, indent=2)}",
    ]
    if dependency_graph:
        sections.append(
            f"## Dependency Graph (flows, triggers, apex DML, business processes)\n"
            f"{json.dumps(dependency_graph, indent=2)}"
        )
    return "\n\n".join(sections)


def _stage5_dynamic_sections(
    complete_tree: list[dict],
    flow_data: dict,
    raw_metadata: dict,
    document_chunks: list[dict],
) -> str:
    excerpts = json.dumps([c["content"][:500] for c in document_chunks[:15]], indent=2) if document_chunks else "None"
    return f"""## Complete Enriched Process Map
{json.dumps(complete_tree, indent=2)}

## Flow Analysis Results
{json.dumps(flow_data, indent=2)}

## Raw Metadata (for validation)
{json.dumps(raw_metadata, indent=2)}

## Document Evidence
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

## Discovered Domains and Their Full Process Hierarchy
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
    document_index: list[dict] | None = None,
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
    middle = _pass1_dynamic_sections(org_context, metadata_summary, document_summary, document_index)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


async def build_stage2_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
) -> str:
    """Stage 2: Structural Decomposition prompt."""
    blocks = await resolve_prompt_blocks("discovery_structure", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning("discovery_prompt_fallback stage=2 block=instructions org_id=%s", org_id)
        instructions = _FALLBACK_STAGE2_INSTRUCTIONS
    if not protocol:
        logger.warning("discovery_prompt_fallback stage=2 block=protocol org_id=%s", org_id)
        protocol = _FALLBACK_STAGE2_PROTOCOL
    middle = _stage2_dynamic_sections(org_context, domain, metadata_detail, document_chunks)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


async def build_stage3_prompt(
    org_id: UUID,
    db: AsyncSession,
    steps: list[dict],
    metadata_per_step: dict[str, dict],
    document_chunks_per_step: dict[str, list[dict]],
) -> str:
    """Stage 3: Step Enrichment prompt."""
    blocks = await resolve_prompt_blocks("discovery_enrichment", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning("discovery_prompt_fallback stage=3 block=instructions org_id=%s", org_id)
        instructions = _FALLBACK_STAGE3_INSTRUCTIONS
    if not protocol:
        logger.warning("discovery_prompt_fallback stage=3 block=protocol org_id=%s", org_id)
        protocol = _FALLBACK_STAGE3_PROTOCOL
    middle = _stage3_dynamic_sections(steps, metadata_per_step, document_chunks_per_step)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


async def build_stage4_prompt(
    org_id: UUID,
    db: AsyncSession,
    enriched_tree: list[dict],
    metadata_relationships: dict,
    dependency_graph: list[dict] | None = None,
) -> str:
    """Stage 4: Flow & Handoff Analysis prompt."""
    blocks = await resolve_prompt_blocks("discovery_flow", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning("discovery_prompt_fallback stage=4 block=instructions org_id=%s", org_id)
        instructions = _FALLBACK_STAGE4_INSTRUCTIONS
    if not protocol:
        logger.warning("discovery_prompt_fallback stage=4 block=protocol org_id=%s", org_id)
        protocol = _FALLBACK_STAGE4_PROTOCOL
    middle = _stage4_dynamic_sections(enriched_tree, metadata_relationships, dependency_graph)
    return f"{instructions}\n\n{middle}\n\n{protocol}"


async def build_stage5_prompt(
    org_id: UUID,
    db: AsyncSession,
    complete_tree: list[dict],
    flow_data: dict,
    raw_metadata: dict,
    document_chunks: list[dict],
) -> str:
    """Stage 5: Validation & Refinement prompt."""
    blocks = await resolve_prompt_blocks("discovery_validation", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if not instructions:
        logger.warning("discovery_prompt_fallback stage=5 block=instructions org_id=%s", org_id)
        instructions = _FALLBACK_STAGE5_INSTRUCTIONS
    if not protocol:
        logger.warning("discovery_prompt_fallback stage=5 block=protocol org_id=%s", org_id)
        protocol = _FALLBACK_STAGE5_PROTOCOL
    middle = _stage5_dynamic_sections(complete_tree, flow_data, raw_metadata, document_chunks)
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
