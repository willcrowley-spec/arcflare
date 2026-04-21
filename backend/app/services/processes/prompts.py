"""Prompt templates for the process discovery pipeline."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.router import PromptParts
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


def _format_technical_modules(technical_modules: list[dict] | None) -> str:
    if not technical_modules:
        return ""
    lines = ["\n## Technical Modules (Auto-detected from metadata dependency analysis)"]
    for mod in technical_modules:
        label = mod.get("label", "Unnamed")
        summary = mod.get("summary", "")
        members = mod.get("members", [])[:10]
        lines.append(f"\n### {label}")
        if summary:
            lines.append(summary)
        if members:
            lines.append("Key members: " + ", ".join(members))
    return "\n".join(lines) + "\n"


def _pass1_dynamic_sections(
    org_context: dict,
    metadata_summary: dict,
    document_summary: list[dict],
    document_index: list[dict] | None = None,
    technical_modules: list[dict] | None = None,
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
{_format_technical_modules(technical_modules)}
## Relevant Document Excerpts
{excerpts}"""


def _stage2_dynamic_sections(
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
    metadata_modules: list[dict] | None = None,
) -> str:
    excerpts = (
        json.dumps(
            [{"content": c["content"], "section": c.get("section_title", "")} for c in document_chunks[:10]],
            indent=2,
        )
        if document_chunks
        else "No relevant documents found."
    )
    modules_section = _format_technical_modules(metadata_modules)
    return f"""## Domain
Name: {domain['name']}
Description: {domain['description']}

## Organization Context
{json.dumps(org_context, indent=2)}

## Detailed Metadata for This Domain
{json.dumps(metadata_detail, indent=2)}
{modules_section}
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
    technical_modules: list[dict] | None = None,
) -> PromptParts:
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
    middle = _pass1_dynamic_sections(
        org_context, metadata_summary, document_summary, document_index, technical_modules
    )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context=middle,
        variable="",
    )


async def build_stage2_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    domain: dict,
    metadata_detail: dict,
    document_chunks: list[dict],
    metadata_modules: list[dict] | None = None,
) -> PromptParts:
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
    org_section = f"## Organization Context\n{json.dumps(org_context, indent=2)}"
    domain_section = _stage2_dynamic_sections(
        org_context, domain, metadata_detail, document_chunks, metadata_modules
    )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context=org_section,
        variable=domain_section,
    )


async def build_stage3_prompt(
    org_id: UUID,
    db: AsyncSession,
    steps: list[dict],
    metadata_per_step: dict[str, dict],
    document_chunks_per_step: dict[str, list[dict]],
) -> PromptParts:
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
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context="",
        variable=middle,
    )


async def build_stage4_prompt(
    org_id: UUID,
    db: AsyncSession,
    enriched_tree: list[dict],
    metadata_relationships: dict,
    dependency_graph: list[dict] | None = None,
) -> PromptParts:
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
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context="",
        variable=middle,
    )


async def build_stage5_prompt(
    org_id: UUID,
    db: AsyncSession,
    complete_tree: list[dict],
    flow_data: dict,
    raw_metadata: dict,
    document_chunks: list[dict],
) -> PromptParts:
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
    metadata_section = f"## Raw Metadata (for validation)\n{json.dumps(raw_metadata, indent=2)}"
    tree_and_flow = (
        f"## Complete Enriched Process Map\n{json.dumps(complete_tree, indent=2)}\n\n"
        f"## Flow Analysis Results\n{json.dumps(flow_data, indent=2)}\n\n"
        f"## Document Evidence\n"
        + (json.dumps([c['content'][:500] for c in document_chunks[:15]], indent=2) if document_chunks else "None")
    )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context=metadata_section,
        variable=tree_and_flow,
    )


_FALLBACK_STAGE3_4_INSTRUCTIONS = """You are a senior business process analyst performing step-level enrichment AND flow analysis in a single pass.

## Part A: Step Enrichment
For each step provided, determine agent-grade operational details using the metadata and documents provided.

### Reasoning Instructions
For each step, trace backward from its artifacts:
1. What event or state change triggers this step?
2. What data does it read or write (specific Object.Field)?
3. What decisions or rules are applied?
4. What constitutes success or failure?

### Evidence Rules
- For system_touchpoints, reference SPECIFIC Object.Field names from the metadata provided. Do NOT invent field names.
- If you cannot identify specific fields for a step, set system_touchpoints to an empty array and set needs_review to true.
- Do NOT assign value_classification "VA" to internal administrative steps. VA means the step directly produces something the external customer receives or experiences.

### Enrichment Fields Per Step
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
11. estimated_frequency — per_transaction, daily, weekly, or monthly

## Part B: Flow & Handoff Analysis
After enriching the steps, identify how they connect to each other and how processes hand off work.

### Flow Reasoning
Trace the data flow in two passes:
1. **Evidence-based connections:** step A writes to an object that step B reads, or an automation triggers after step A and modifies data for step B.
2. **Inferred connections:** steps that logically must be sequential but have no metadata evidence — mark type as "inferred" with confidence < 0.5.

### Parallel Detection
If two steps read from the same trigger but write to different objects with no dependency between them, they may execute in parallel. Group them.

### Handoff Data Contracts
For each handoff between processes, identify what data transfers — list specific Object.Field combinations that cross the boundary."""

_FALLBACK_STAGE3_4_PROTOCOL = """Return a JSON object matching the enforced schema containing BOTH enriched_steps (with all enrichment fields) AND step_flows/handoffs/parallel_groups/entry_points/terminal_points."""


def _stage3_4_dynamic_sections(
    steps: list[dict],
    metadata_per_step: dict[str, dict],
    document_chunks_per_step: dict[str, list[dict]],
    enriched_tree: list[dict],
    metadata_relationships: dict,
    dependency_graph: list[dict] | None = None,
) -> str:
    step_sections = []
    for step in steps:
        name = step["name"]
        meta = json.dumps(metadata_per_step.get(name, {}), indent=2)
        docs = json.dumps(
            [c["content"] for c in document_chunks_per_step.get(name, [])[:5]],
            indent=2,
        )
        step_sections.append(f"""### Step: "{name}"
Artifacts: {json.dumps(step.get("artifacts", []))}
Relevant metadata:
{meta}
Relevant documents:
{docs}""")

    flow_sections = [
        f"## Enriched Process Hierarchy\n{json.dumps(enriched_tree, indent=2)}",
        f"## Metadata Relationships (lookups, automations)\n{json.dumps(metadata_relationships, indent=2)}",
    ]
    if dependency_graph:
        flow_sections.append(
            f"## Dependency Graph (flows, triggers, apex DML, business processes)\n"
            f"{json.dumps(dependency_graph, indent=2)}"
        )
    return "## Steps to Enrich\n\n" + "\n\n".join(step_sections) + "\n\n" + "\n\n".join(flow_sections)


async def build_stage3_4_prompt(
    org_id: UUID,
    db: AsyncSession,
    steps: list[dict],
    metadata_per_step: dict[str, dict],
    document_chunks_per_step: dict[str, list[dict]],
    enriched_tree: list[dict],
    metadata_relationships: dict,
    dependency_graph: list[dict] | None = None,
) -> PromptParts:
    """Stage 3+4 merged: Enrichment + Flow prompt."""
    blocks = await resolve_prompt_blocks("discovery_enrichment_flow", org_id, db)
    instructions = blocks.get("instructions") or ""
    protocol = blocks.get("protocol") or ""
    middle = _stage3_4_dynamic_sections(
        steps, metadata_per_step, document_chunks_per_step,
        enriched_tree, metadata_relationships, dependency_graph,
    )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context="",
        variable=middle,
    )


_V2_PHASE1_INSTRUCTIONS = """You are a senior business process analyst. Given the following information about an organization and its technology systems, identify the top-level business process domains.

## Reasoning Instructions
Before listing domains, reason step by step:
1. What business capabilities does this organization's metadata reveal?
2. Which clusters of metadata objects belong together by naming convention, shared relationships, or automation chains?
3. Which document summaries describe end-to-end workflows?
4. What are the natural boundaries between different business functions?

## Domain Quality Criteria
- Each domain should own 3-30 metadata objects. A domain with 1 object is too narrow. A domain with 50+ is too broad.
- Domains must reflect business capabilities (e.g., "Customer Support Operations"), NOT platform product names (e.g., "Service Cloud").
- Do NOT create catch-all domains like "General Administration".

## Instructions
For each domain:
- Name it clearly (e.g., "Sales Operations", "Claims Processing")
- Describe what it encompasses
- List 3-8 key_objects: the Salesforce API names of objects CENTRAL to this domain (these drive retrieval)
- List 3-6 key_terms: business terms associated with this domain (used for document search)
- Rate your confidence from 0.0 to 1.0
- Explain your reasoning briefly"""

_V2_PHASE1_PROTOCOL = """Return a JSON object matching the enforced schema:
{
  "domains": [
    {
      "name": "string",
      "description": "string",
      "confidence": 0.0,
      "key_objects": ["Lead", "Campaign"],
      "key_terms": ["lead scoring", "qualification"],
      "reasoning": "string"
    }
  ]
}"""

_V2_PHASE3_INSTRUCTIONS = """You are a senior business process analyst building an operational profile for Agentic Business Operating Systems (ABOS) assessment. Given an evidence bundle for a single business domain, extract the complete process hierarchy with enough operational detail to evaluate which steps can be replaced by agentic AI workers.

## CRITICAL: Citation Requirement
Every process, step, actor, touchpoint, trigger, and decision MUST cite at least one evidence reference using the tagged IDs (e.g., [OBJ-1], [AUTO-3], [DOC-5]). Claims without citations will be rejected in verification.

## Purpose: ABOS Readiness Profiling
The output of this extraction will be used to recommend which business processes can be automated by agentic workers. For each process and step, you must capture:
- WHO does the work (actors) — named roles, integrations, or system automations, not generic labels like "user"
- WHAT triggers the work — specific events, field changes, schedules, or conditions from the evidence
- WHAT systems are touched — specific object names, operations, and if visible, specific fields
- WHAT decisions are made — the rules, thresholds, or judgments applied
- WHAT can go wrong — failure modes and their recovery paths
- HOW suitable for automation — based on rule-based vs judgment-based, data availability, exception rate

## Hierarchy
- **Process** — a complete business workflow with a clear trigger and outcome (e.g., "Lead Qualification"). Has 2-8 children.
- **Subprocess/Step** — atomic units of work or logical groupings within a process. If a step contains "and", split it.

## Extraction Rules
1. Derive processes ONLY from the evidence provided. Do not hallucinate processes that have no metadata or document support.
2. For system_touchpoints, reference SPECIFIC object and automation names from the evidence. Do NOT invent names.
3. For actors, use specific role names visible in the evidence (e.g., "Sales Rep via Lead object owner field", "Scheduled Flow: Lead_Score_Calculation"). Do NOT use generic labels like "User" or "Admin" unless that is literally what the evidence shows.
4. For trigger_conditions, cite the specific automation trigger type, field change, or schedule from the evidence. "Record created" is not enough — say which object and what trigger type.
5. For automation_potential, consider: Is the step fully rule-based with structured data? (high) Does it require human judgment on unstructured data? (low) Is there partial automation already via flows/triggers? (medium — cite the existing automation)
6. If you cannot find evidence for a claim, do NOT include it. Absence is better than fabrication.
7. Set needs_review=true for anything with confidence < 0.6.
8. Value classification: VA = directly produces customer-facing value, BVA = business-necessary but internal, NVA = waste/rework/manual workaround."""

_V2_PHASE3_PROTOCOL = """Return a JSON object with "processes" array and optional "intra_domain_handoffs" array.

REQUIRED for every process and child step:
- evidence_refs: at least one tagged reference (e.g., OBJ-1, AUTO-3)
- actors: at least one, with specific name and type (user/integration/system)
- trigger_conditions: at least one, with description citing evidence
- system_touchpoints: at least one, with specific object/automation name and operation
- value_classification: VA, BVA, or NVA
- automation_potential: high, medium, low, or none — with reasoning implicit in the context
- complexity_score: low, medium, or high

If you truly cannot determine a required field from the evidence, set needs_review=true and provide your best inference."""

_V2_PHASE4_INSTRUCTIONS = """You are a verification analyst. Your job is to check whether evidence citations actually support the claims made about business processes.

## Instructions
For each claim-evidence pair below, determine:
- CONFIRMED: The evidence directly and clearly supports the claim.
- WEAK: The evidence is tangentially related but doesn't strongly support the specific claim.
- UNSUPPORTED: The evidence does not support the claim at all, or the claim extrapolates well beyond what the evidence shows.

Be skeptical. A claim that "Lead scoring happens nightly" requires evidence of a scheduled job, not just the existence of a score field."""

_V2_PHASE4_PROTOCOL = """Return a JSON object with a "verifications" array. Each entry must have: process_name, claim, evidence_ref, verdict (CONFIRMED/WEAK/UNSUPPORTED), and reasoning."""

_V2_PHASE5_INSTRUCTIONS = """You are a senior business process analyst performing cross-domain synthesis. You have verified process trees from multiple domains.

## Instructions
1. Identify cross-domain handoffs: where Domain A's output feeds Domain B's input. Cite evidence (e.g., shared objects, automations that bridge domains).
2. Flag gaps: domains that logically should connect but share zero evidence.
3. Categorize orphaned artifacts that no domain claimed.
4. Write a 2-3 paragraph executive summary: (1) core value flow, (2) supporting operations, (3) gaps and automation opportunities.
5. Generate a short narrative per domain."""

_V2_PHASE5_PROTOCOL = """Return a JSON object with: cross_domain_handoffs, orphaned_artifacts, domain_narratives, executive_summary."""


def _v2_phase1_dynamic(
    org_context: dict,
    object_inventory: list[dict],
    metadata_community_summaries: list[dict],
    document_community_summaries: list[dict],
) -> str:
    lines = [
        f"## Organization\nName: {org_context.get('name', 'Unknown')}",
        f"Industry: {org_context.get('industry', 'Unknown')}",
        f"Business Model: {org_context.get('business_model', '')}",
    ]
    desc = org_context.get("description", "")
    if desc:
        lines.append(f"Description: {desc}")

    lines.append(f"\n## Object Inventory ({len(object_inventory)} objects with data)")
    for obj in object_inventory[:60]:
        lines.append(f"  {obj['api_name']} — {obj.get('record_count', 0)} records")

    if metadata_community_summaries:
        lines.append("\n## Metadata Clusters (auto-detected)")
        for mod in metadata_community_summaries[:10]:
            label = mod.get("label", "Unnamed")
            summary = mod.get("summary", "")
            lines.append(f"  ### {label}")
            if summary:
                lines.append(f"  {summary}")

    if document_community_summaries:
        lines.append("\n## Document Themes")
        for mod in document_community_summaries[:5]:
            label = mod.get("label", "Unnamed")
            summary = mod.get("summary", "")
            lines.append(f"  ### {label}")
            if summary:
                lines.append(f"  {summary}")

    return "\n".join(lines)


async def build_v2_phase1_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    object_inventory: list[dict],
    metadata_community_summaries: list[dict],
    document_community_summaries: list[dict],
) -> PromptParts:
    """v2 Phase 1: Domain Discovery with key_objects and key_terms."""
    blocks = await resolve_prompt_blocks("discovery_v2_domain", org_id, db)
    instructions = blocks.get("instructions") or ""
    protocol = blocks.get("protocol") or ""
    context = _v2_phase1_dynamic(
        org_context, object_inventory,
        metadata_community_summaries, document_community_summaries,
    )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context=context,
        variable="",
    )


async def build_v2_phase3_prompt(
    org_id: UUID,
    db: AsyncSession,
    domain: dict,
    evidence_text: str,
) -> PromptParts:
    """v2 Phase 3: Per-domain extraction from evidence bundle."""
    blocks = await resolve_prompt_blocks("discovery_v2_extraction", org_id, db)
    instructions = blocks.get("instructions") or ""
    protocol = blocks.get("protocol") or ""
    task = (
        f"Extract all business processes for the \"{domain['name']}\" domain.\n"
        f"Domain description: {domain.get('description', '')}\n\n"
        "## Your task\n"
        "Build a complete operational profile of this domain for ABOS readiness assessment.\n"
        "For every process and step:\n"
        "1. Cite specific evidence (OBJ-x, AUTO-x, DOC-x) for every claim\n"
        "2. Name specific actors, triggers, and system touchpoints from the evidence\n"
        "3. Assess automation_potential based on whether the step is rule-based with structured data (high) or judgment-heavy (low)\n"
        "4. Classify value: VA (customer-facing), BVA (business-necessary), NVA (waste/workaround)\n"
    )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context=evidence_text,
        variable=task,
    )


async def build_v2_phase4_prompt(
    org_id: UUID,
    db: AsyncSession,
    verification_pairs: list[dict],
) -> PromptParts:
    """v2 Phase 4: Evidence verification."""
    blocks = await resolve_prompt_blocks("discovery_v2_verification", org_id, db)
    instructions = blocks.get("instructions") or ""
    protocol = blocks.get("protocol") or ""
    pairs_text = []
    for i, pair in enumerate(verification_pairs):
        pairs_text.append(
            f"--- Pair {i + 1} ---\n"
            f"Process: {pair['process_name']}\n"
            f"Claim: {pair['claim']}\n"
            f"Evidence [{pair['evidence_ref']}]: {pair['evidence_text']}\n"
        )
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context="",
        variable="\n".join(pairs_text),
    )


async def build_v2_phase5_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    domain_summaries: list[dict],
    cross_domain_edges: list[dict],
    orphaned_objects: list[str],
    orphaned_automations: list[str],
) -> PromptParts:
    """v2 Phase 5: Cross-domain synthesis."""
    blocks = await resolve_prompt_blocks("discovery_v2_synthesis", org_id, db)
    instructions = blocks.get("instructions") or ""
    protocol = blocks.get("protocol") or ""

    context_lines = [
        f"## Organization: {org_context.get('name', 'Unknown')}",
        f"Industry: {org_context.get('industry', 'Unknown')}",
    ]

    context_lines.append("\n## Verified Domain Process Trees")
    for ds in domain_summaries:
        context_lines.append(f"\n### {ds['domain_name']}")
        for proc in ds.get("processes", []):
            context_lines.append(f"  - {proc['name']} (confidence: {proc.get('confidence', 0)})")
            key_objs = [
                e.get("api_name", "") for e in proc.get("evidence_sources", [])
                if e.get("type") == "metadata_object"
            ]
            if key_objs:
                context_lines.append(f"    Objects: {', '.join(key_objs)}")

    if cross_domain_edges:
        context_lines.append("\n## Cross-Domain Dependency Edges")
        for e in cross_domain_edges[:20]:
            context_lines.append(
                f"  {e['source']} ({e.get('source_domain', '?')}) → "
                f"{e['target']} ({e.get('target_domain', '?')}) [{e.get('relationship', '')}]"
            )

    orphaned_section = []
    if orphaned_objects:
        orphaned_section.append("Objects: " + ", ".join(orphaned_objects[:30]))
    if orphaned_automations:
        orphaned_section.append("Automations: " + ", ".join(orphaned_automations[:30]))
    if orphaned_section:
        context_lines.append("\n## Unclaimed Artifacts")
        context_lines.extend(orphaned_section)
    else:
        context_lines.append("\n## Unclaimed Artifacts\nAll artifacts are accounted for.")

    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context="\n".join(context_lines),
        variable="",
    )


async def build_pass3_prompt(
    org_id: UUID,
    db: AsyncSession,
    org_context: dict,
    all_domains: list[dict],
    orphaned_artifacts: list[dict],
) -> PromptParts:
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
    return PromptParts(
        system=f"{instructions}\n\n{protocol}",
        context=middle,
        variable="",
    )
