---
name: process-mapping
description: Codifies hierarchy definitions, quality heuristics, value classification, antipatterns, and enrichment criteria for the Arcflare process discovery pipeline. Reference when writing or reviewing discovery prompts, pipeline stage code, or quality scoring logic.
---

# Process Mapping Intelligence

## When to Use

Use this skill when:
- Writing or modifying discovery pipeline prompts (Stages 1-6)
- Reviewing LLM output from process discovery
- Implementing or debugging pipeline stage code
- Defining quality scoring metrics (Stage 7)
- Evaluating whether a discovery run output meets enterprise standards

## Hierarchy Definitions (BPMN-derived)

| Level | Definition | BPMN Equivalent | Children Range | Example |
|-------|-----------|-----------------|----------------|---------|
| **Domain** | Top-level business capability area | Pool | 2-10 processes | "Sales Operations" |
| **Process** | Complete workflow with clear trigger and outcome | Process | 2-8 children | "Lead Qualification" |
| **Subprocess** | Logical grouping within a process | Sub-Process | 2-6 children | "Initial Scoring" |
| **Step** | Atomic unit of work by one actor in one system | Task | 0 (leaf node) | "Update Lead Status" |

### Depth Rules
- Most domains: 2-3 levels deep
- Maximum: 4 levels (only with strong evidence)
- Steps are always leaf nodes
- Every non-leaf must have >= 2 children

### Object Ownership
- A domain should own 3-30 metadata objects
- 1 object = too narrow (merge into another domain)
- 50+ objects = too broad (split into multiple domains)

## Quality Heuristics

### Structural Quality
- Process with >8 direct children → split into subprocesses
- Domain with 1 process → merge into related domain or re-examine
- Step containing "and" → split into two steps (atomicity violation)
- Process with 0 steps → empty container, likely incomplete

### Confidence Calibration
- Step with confidence >0.8 must have >= 1 Object.Field in system_touchpoints
- Step with zero touchpoints should have confidence <= 0.5
- Handoff with no metadata evidence should have confidence <= 0.4
- Domain with >80% of org objects should be flagged for review

### Evidence Grounding
- Every claim must reference specific metadata or document evidence
- "Integration" handoff type requires an automation artifact citation
- "Automated" handoff type requires a Flow or Trigger citation
- Steps referencing non-existent metadata → phantom_reference issue

## Value Classification (Lean Value Stream)

| Classification | Definition | Signal | Example |
|---------------|-----------|--------|---------|
| **VA** (Value-Added) | Directly serves the external customer | Customer would pay for this | "Generate quote document" |
| **BVA** (Business Value-Added) | Necessary for the business but not customer-facing | Regulatory, compliance, internal reporting | "Run credit check" |
| **NVA** (Non-Value-Added) | Waste, rework, unnecessary handoffs | Manual data entry, approval bottlenecks, duplicate entry | "Re-enter data from email into CRM" |

### Classification Rules
- Internal administrative steps are BVA or NVA, never VA
- Approval steps are typically BVA (necessary but not customer-value)
- Manual data transfer between systems is NVA
- Error correction / rework is always NVA

## Enrichment Field Definitions

| Field | What It Captures | Quality Signal |
|-------|-----------------|---------------|
| `trigger_conditions` | Event or state change that initiates the step | Must reference a real object/field if automated |
| `decision_logic` | Branching rules applied during or after the step | Must cite evidence (validation rule, flow branch) |
| `system_touchpoints` | Specific Object.Field interactions (read/write/create) | Must reference real metadata — never invented names |
| `success_criteria` | How to know the step completed correctly | At least one measurable criterion preferred |
| `failure_modes` | What can go wrong and recovery path | Include impact assessment |
| `value_classification` | VA / BVA / NVA | Follow Lean rules above |
| `complexity_score` | low / medium / high for automation difficulty | Based on system count and judgment requirement |
| `automation_potential` | high / medium / low / none for automation suitability | Independent from complexity — rule-based + data-available = high |
| `estimated_duration` | minutes / hours / days per execution | Inferred from automation type and manual indicators |
| `estimated_frequency` | per_transaction / daily / weekly / monthly | Inferred from trigger type and batch patterns |

## Antipatterns

### Domain-Level
- **Catch-all domains:** "General Administration", "Miscellaneous", "Other" → evidence of incomplete analysis
- **Product-name domains:** "Service Cloud", "Marketing Cloud" → these are platforms, not business capabilities
- **Single-object domains:** domain with only 1 metadata object → too granular, merge up

### Process-Level
- **Compound steps:** "Review and Approve" → split into "Review" then "Approve"
- **Phantom handoffs:** handoff asserted without any metadata or document evidence
- **Empty containers:** process or subprocess with zero children
- **Over-decomposition:** domain with >15 direct processes before any subprocess grouping

### Enrichment-Level
- **Invented field names:** system_touchpoints referencing Object.Field that doesn't exist in metadata
- **VA inflation:** marking internal steps as Value-Added
- **Missing touchpoints:** step with high confidence but empty system_touchpoints
- **Catch-all actors:** "System" as the only actor for every step

## Quality Scoring Rubric (Stage 7)

| Metric | Formula | Weight | Target |
|--------|---------|--------|--------|
| `metadata_coverage` | % of non-deprecated objects/automations referenced by >= 1 step | 0.25 | > 70% |
| `step_specificity` | % of steps with >= 1 Object.Field in system_touchpoints | 0.25 | > 60% |
| `handoff_grounding` | % of handoffs with metadata evidence (not inferred/unknown) | 0.20 | > 50% |
| `hierarchy_consistency` | 1 - normalized std_dev of depth across domains | 0.15 | > 0.7 |
| `value_coverage` | % of steps with non-null value_classification | 0.15 | > 80% |
| `overall` | Weighted sum of above | 1.0 | > 0.6 |
