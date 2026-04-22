# Agent Opportunity Engine — Domain-Level Agentforce Recommendation Pipeline

**Date:** 2026-04-21
**Status:** Draft
**Replaces:** [Recommendation Pipeline v1](2026-04-20-recommendation-pipeline-design.md) (per-process heuristic + LLM scoring)
**Depends on:** [Discovery Pipeline v2](2026-04-20-discovery-pipeline-v2-design.md) (consumes its output)

## Problem

The current recommendation engine operates at the wrong altitude. It generates one recommendation per process/subprocess row, asks "can this be automated?", scores it with a heuristic + LLM blend, and projects ROI. This produces a list of isolated process-level automation suggestions — not a coherent picture of where Agentforce agents should be built.

The real question isn't "can Process X be automated?" — it's "looking at everything happening in this domain, what agents should exist?" A single Agentforce agent can own multiple topics spanning multiple processes and steps. The engine should identify those agent-shaped opportunities by analyzing entire process domains, not individual rows.

Additionally, the current engine treats deterministic, agentic, and hybrid automation as equal recommendation types. The desired output is agent recommendations — opportunities where Agentforce agents (which inherently blend deterministic logic with LLM reasoning) can replace or augment manual work. Purely deterministic Flow-level automations are not the target.

## Goal

Build a recommendation engine that:

1. Analyzes entire process domains (all processes, steps, handoffs, actors, decision logic, system touchpoints) as a unit
2. Identifies agent opportunities — coherent clusters of work that a single Agentforce agent could own across multiple processes and steps
3. Assesses feasibility against real Agentforce capabilities (topics, actions, variables, headless vs. conversational, Apex middleware requirements)
4. Produces opportunity cards with enough embedded signals for asynchronous financial evaluation
5. Detects cross-domain agent opportunities that span multiple business domains
6. Does NOT produce one recommendation per process step
7. Does NOT recommend purely deterministic workflows (those are Flows, not agents)

## Architecture: 4-Phase Pipeline

```
Phase 1: Domain Context Assembly          (pure code, no LLM)
    For each domain in the discovery run, assemble a structured
    context document from the process tree, steps, handoffs, actors,
    touchpoints, and decision logic.
              |
              v
Phase 2: Agent Opportunity Analysis       (LLM, per domain)
    One call per domain. Input: domain context + Agentforce capability
    reference. Output: agent opportunity cards.
              |
              v
Phase 3: Cross-Domain Synthesis           (LLM, one call, optional)
    Sees opportunity summaries from all domains. Proposes agents that
    span domain boundaries or suggests merging related opportunities.
              |
              v
Phase 4: Financial Signal Enrichment      (async, post-commit)
    Separate Celery task. Reads financial_signals from each opportunity,
    assembles assumptions, runs compute_projections, writes back
    scenarios_json and estimated_roi.
```

### Why This Shape

- **Phase 1 is deterministic and auditable.** Data assembly is pure code — testable, fast, cacheable. No tokens burned. The domain context document is inspectable.
- **Phase 2 is one focused LLM job per domain.** The LLM sees the complete picture (processes, steps, actors, handoffs, touchpoints) and makes agent boundary decisions with Agentforce knowledge. One call per domain keeps latency proportional to org size.
- **Phase 3 catches what per-domain analysis misses.** Cross-domain agents (same actor doing similar work in different domains) and handoff bridging agents only emerge when you see the full org picture.
- **Phase 4 decouples identification from evaluation.** Agent opportunity identification returns fast. Financial projections run async and write back when ready. The UI can show opportunities immediately and fill in financial data as it arrives.

---

## Phase 1: Domain Context Assembly

**Module:** `backend/app/services/recommendations/domain_assembler.py`

Pure Python + SQL. No LLM calls. Replaces `candidate_generator.py`.

### Query Scope

All `BusinessProcess` rows for the latest completed `DiscoveryRun` for the org, at **all levels** — domain, process, subprocess, step. The current engine filters to `level.in_(("process", "subprocess"))` and throws away step-level data. The new engine uses the full tree.

All `ProcessHandoff` rows for the same discovery run.

### Output Per Domain

```python
@dataclass
class DomainContext:
    domain: DomainSummary
    processes: list[ProcessContext]
    handoffs: list[HandoffContext]
    actor_roster: dict[str, list[str]]       # actor -> [process > step, ...]
    system_touchpoints: dict[str, list[str]]  # object -> [field, ...]

@dataclass
class DomainSummary:
    id: UUID
    name: str
    description: str | None
    narrative: str | None

@dataclass
class ProcessContext:
    id: UUID
    name: str
    level: str
    description: str | None
    narrative: str | None
    actors: list
    trigger_conditions: list
    decision_logic: list
    system_touchpoints: list
    failure_modes: list
    value_classification: str | None
    complexity_score: str | None
    automation_potential: str | None
    estimated_duration: str | None
    estimated_frequency: str | None
    steps: list[StepContext]

@dataclass
class StepContext:
    id: UUID
    name: str
    level: str  # "step" or "subprocess"
    actors: list
    decision_logic: list
    trigger_conditions: list
    system_touchpoints: list
    failure_modes: list
    estimated_duration: str | None
    estimated_frequency: str | None
    sequencing: dict
    value_classification: str | None
    complexity_score: str | None

@dataclass
class HandoffContext:
    source_process_name: str
    target_process_name: str
    handoff_type: str
    is_gap: bool
    description: str | None
```

### Derived Views

Two cross-cutting views are assembled from the raw data:

**Actor Roster:** Deduplicates all actors across the domain and maps each to the processes/steps where they appear. This gives the LLM a role-oriented view of the domain — e.g., "Sales Rep appears in Lead Qualification > BANT Scoring, Lead Assignment > Territory Routing, and Opportunity Creation > Initial Setup."

**System Touchpoint Inventory:** Deduplicates all Salesforce objects and fields across the domain. Groups by object. This gives the LLM a data-oriented view — e.g., "Lead: Status, Rating, BANT_Score__c; Opportunity: StageName, Amount, CloseDate."

Both are natural agent boundary signals. Steps that share actors or data context are candidates for belonging to the same agent.

### Token Management

For large domains, the context document could exceed useful sizes. Strategy:

1. Always include full process-level detail (these are the structural backbone).
2. For steps, include full detail for up to 8 steps per process. If a process has more, include the 8 with the highest complexity_score and summarize the rest as a count with their names.
3. Estimate token count before serialization. Target: 40k tokens max per domain context. If exceeded, progressively truncate step-level `failure_modes` and `trigger_conditions` (least critical for agent boundary decisions).

### Serialization

The `DomainContext` serializes to a JSON document for the LLM prompt. The assembler also returns the raw dataclass for programmatic access (e.g., building `linked_process_ids` and `linked_step_ids` from the LLM's response).

---

## Phase 2: Agent Opportunity Analysis

**Module:** `backend/app/services/recommendations/agent_analyzer.py`

One LLM call per domain. Replaces `llm_scorer.py`.

### Operation Config

```python
"agent_opportunity": {
    "model": "anthropic/claude-sonnet-4-6",
    "tier": "strong",
    "thinking_budget": 16000,
    "output_format": "json",
    "label": "Agent Opportunity Analysis",
    "group": "synthesis",
    "description": "Domain-level analysis identifying Agentforce agent opportunities across processes and steps.",
}
```

Higher thinking budget than the current `recommendations` operation (10000) because the task is more complex — the LLM needs to reason about agent boundaries across an entire domain.

### Prompt Structure

The prompt has three sections:

1. **System prompt:** Agent opportunity analyst identity + Agentforce Knowledge Reference (see dedicated section below)
2. **User prompt:** Serialized `DomainContext` JSON
3. **Output protocol:** Required JSON shape for agent opportunity cards

### Output Protocol

```json
{
    "agent_opportunities": [
        {
            "agent_name": "string — descriptive name for the proposed agent",
            "agent_type": "headless | conversational | hybrid",
            "description": "2-3 sentences: what this agent does, who it serves, what business outcome it drives",

            "topics": [
                {
                    "topic_name": "string — name for this topic/job",
                    "description": "What this topic handles",
                    "reasoning_type": "deterministic | agentic | hybrid",
                    "actions_needed": ["List of actions/tools this topic would call"]
                }
            ],

            "replaces": [
                {
                    "process_id": "uuid from the input",
                    "process_name": "string",
                    "steps_replaced": ["step names from the input"],
                    "step_ids": ["step uuids from the input"],
                    "replacement_type": "full | partial"
                }
            ],

            "trigger": "What kicks this agent off (record event, user request, schedule, etc.)",
            "data_requirements": ["Salesforce objects this agent needs access to"],
            "integration_points": ["External systems or APIs that need Apex middleware"],

            "complexity_estimate": "low | medium | high",
            "confidence": "0.0-1.0 — how confident you are this is a viable agent",
            "rationale": "Why these processes/steps belong together as one agent and why an agent (not a Flow) is the right solution",
            "risks": "Key implementation risks or feasibility concerns",

            "financial_signals": {
                "actors_impacted": ["role names affected by this agent"],
                "estimated_hours_per_week_saved": "number",
                "estimated_frequency": "daily | weekly | monthly | ad-hoc",
                "estimated_actor_count": "number of people currently doing this work",
                "primary_role_type": "the dominant role type for salary estimation"
            }
        }
    ],
    "uncovered_processes": [
        {
            "process_name": "string",
            "reason": "Why this process wasn't included in any agent opportunity"
        }
    ]
}
```

The `uncovered_processes` array is important — it explicitly surfaces processes that the LLM decided don't belong in any agent opportunity (purely manual creative work, already well-automated, too simple for an agent, etc.). This prevents the "where did Process X go?" question.

### ID Resolution

The LLM outputs process names and step names. After the LLM call, the analyzer resolves these back to UUIDs using the `DomainContext` dataclass (which has the full ID mappings). Fuzzy matching on names handles minor LLM name variations. Unresolvable references are logged and dropped.

---

## Agentforce Knowledge Reference

Injected into the Phase 2 system prompt. ~3.5k tokens total. Four sections.

### Section 1: Capability Model (~500 tokens)

```
AGENTFORCE AGENT CAPABILITIES:

An Agentforce agent can:
- Own multiple "topics" (distinct jobs) — each topic has its own actions and reasoning
- Route between topics based on user input or data conditions
- Execute deterministic logic (if/then, field updates, record queries) before LLM reasoning
- Use LLM reasoning for judgment calls: classification, prioritization, content generation,
  exception handling, contextual decision-making
- Call Apex actions (database queries, API callouts, complex business logic)
- Call Flow actions (record operations, simple automations)
- Carry mutable state across topics via global variables
- Operate conversationally (user-facing, can ask questions and present options)
  OR headlessly (triggered by record events or Flows, no user interaction, fully autonomous)
- Handle structured data (Salesforce records, fields) and unstructured data
  (emails, free text, case descriptions)
- Gate topic availability behind conditions (authentication status, data loaded, role checks)
- Pre-load data deterministically before the LLM reasons (so the LLM has context from
  the first turn)

An agent CANNOT:
- Call external APIs directly — any integration outside Salesforce needs Apex middleware
- Run long-duration background processes (agents are request-response per turn)
- Process files or documents natively (needs Apex for parsing)
- Replace complex multi-org or multi-cloud orchestration
- Maintain state between separate sessions (state is per-session only)
```

### Section 2: Design Principles (~600 tokens)

```
AGENT DESIGN PRINCIPLES:

1. ONE AGENT = ONE DOMAIN OF RESPONSIBILITY
   An agent owns a coherent area of work, not a single task. Think "Sales Qualification
   Agent" (owns the full qualification workflow) not "BANT Scoring Agent" (too narrow —
   that's a topic within an agent, not a standalone agent).

2. TOPICS = JOBS WITHIN THAT RESPONSIBILITY
   Each topic handles one distinct job the agent can do. An agent with 3-6 topics is
   typical. More than 8 topics suggests the agent scope is too broad.

3. GROUP BY SHARED CONTEXT, NOT PROCESS BOUNDARIES
   Organizational process boundaries don't map to optimal agent boundaries. Look for:
   - Steps that touch the same data objects (same records, same fields)
   - Steps performed by the same actor/role across different processes
   - Steps with similar decision patterns (all routing decisions, all classification tasks)
   - Sequential handoffs that an agent could eliminate entirely

4. HEADLESS WHEN NO HUMAN INPUT NEEDED
   If the work is triggered by a data event and requires no human interaction, the agent
   is headless. If a user provides information or makes choices, it's conversational.
   Many agents are hybrid: triggered by an event but may need to interact with a user
   for certain topics.

5. DETERMINISTIC CORE + AGENTIC EDGE CASES
   Most real agents blend deterministic and agentic reasoning. The deterministic layer
   handles the predictable 80% (field updates, rule checks, routing). The LLM handles
   ambiguity, classification of unstructured inputs, and exception logic.

6. FLAG INTEGRATION REQUIREMENTS HONESTLY
   Every external system touchpoint needs Apex middleware. This is real implementation
   work. Don't hide it — flag it as a requirement and a complexity driver.
```

### Section 3: Antipatterns (~400 tokens)

```
ANTIPATTERNS — DO NOT RECOMMEND THESE:

- ONE AGENT PER PROCESS STEP: A single step is a topic at most, never a standalone agent.
  Always look across processes to find where one agent owns multiple related steps.

- PURELY DETERMINISTIC AGENTS: If every topic in the proposed agent is just if/then logic
  with no LLM reasoning anywhere, it should be a Flow, not an agent. Only recommend agents
  where there is genuine judgment, classification, unstructured data handling, or contextual
  decision-making.

- NOTIFICATION-ONLY AGENTS: An agent that only sends emails or creates tasks without making
  any decisions adds no value over a simple automation rule. Agents must reason.

- BOIL-THE-OCEAN AGENTS: Don't propose one mega-agent that replaces everything in a domain.
  Find the highest-value coherent cluster of related work. If a domain has 15 processes,
  the answer is probably 2-4 focused agents, not 1 agent with 15 topics.

- IGNORING INTEGRATION COMPLEXITY: An agent needing 5+ external API integrations is
  high-risk and high-effort. Be honest about this in complexity_estimate and risks.

- REDUNDANT AGENTS: Don't propose two agents that overlap significantly. If two opportunities
  share most of their data context and actors, merge them into one agent with more topics.
```

### Section 4: Worked Examples (~2k tokens)

```
EXAMPLE 1 — Headless Agent Spanning Multiple Processes:

Domain: "Order Management"
Processes observed: Order Validation (3 steps), Inventory Check (2 steps),
  Shipping Assignment (4 steps), Exception Handling (3 steps)
Handoffs: Order Validation -> Inventory Check (manual, gap),
  Inventory Check -> Shipping Assignment (manual, gap)

Recommended agent:
{
  "agent_name": "Order Fulfillment Agent",
  "agent_type": "headless",
  "description": "Triggered by Order status change to 'Submitted'. Validates order
    completeness, allocates inventory with backorder prioritization, and routes to
    the optimal shipping carrier. Eliminates 2 manual handoff gaps and reduces
    fulfillment cycle time from ~4 hours to minutes for standard orders.",
  "topics": [
    {
      "topic_name": "Order Validation",
      "reasoning_type": "deterministic",
      "description": "Checks required fields, payment verification, address validation",
      "actions_needed": ["Query Order fields", "Validate payment status", "Flag incomplete orders"]
    },
    {
      "topic_name": "Inventory Allocation",
      "reasoning_type": "hybrid",
      "description": "Deterministic stock check for standard items; LLM reasoning for
        backorder prioritization when multiple orders compete for limited stock",
      "actions_needed": ["Query inventory levels", "Reserve stock", "Prioritize backorders"]
    },
    {
      "topic_name": "Shipping Routing",
      "reasoning_type": "agentic",
      "description": "Analyzes delivery requirements, package dimensions, destination,
        and cost constraints to select optimal carrier and service level",
      "actions_needed": ["Get shipping quotes (Apex middleware)", "Create shipment record"]
    }
  ],
  "replaces": [
    {"process_name": "Order Validation", "steps_replaced": ["Field Check", "Payment Verify", "Address Validate"], "replacement_type": "full"},
    {"process_name": "Inventory Check", "steps_replaced": ["Stock Lookup", "Allocation"], "replacement_type": "full"},
    {"process_name": "Shipping Assignment", "steps_replaced": ["Carrier Selection", "Rate Comparison", "Label Generation"], "replacement_type": "partial"}
  ],
  "trigger": "Order.Status changed to 'Submitted'",
  "data_requirements": ["Order", "OrderItem", "Product2", "Shipment"],
  "integration_points": ["Shipping carrier API (needs Apex middleware)"],
  "complexity_estimate": "medium",
  "confidence": 0.85,
  "rationale": "These three processes form a linear pipeline with two manual handoff gaps.
    Same data context (Order records), sequential execution, and the handoff gaps represent
    pure wait time. One headless agent eliminates both gaps.",
  "risks": "Shipping carrier API integration is the main complexity driver. Backorder
    prioritization logic may need business rules that aren't captured in current process data."
}


EXAMPLE 2 — Conversational Agent Across Support Processes:

Domain: "Customer Support"
Processes observed: Ticket Triage (3 steps), Knowledge Search (2 steps),
  Escalation Routing (3 steps), Resolution Documentation (2 steps)

Recommended agent:
{
  "agent_name": "Support Resolution Agent",
  "agent_type": "conversational",
  "description": "User-facing agent for support representatives. Classifies incoming
    cases from free-text descriptions, searches the knowledge base for solutions,
    proposes resolutions, and handles escalation routing when the agent can't resolve.
    Replaces the manual triage-search-resolve cycle.",
  "topics": [
    {
      "topic_name": "Case Classification",
      "reasoning_type": "agentic",
      "description": "Classifies case from free-text description into category, priority,
        and product area. Handles ambiguous descriptions that don't fit clean categories.",
      "actions_needed": ["Update Case.Category", "Update Case.Priority", "Query similar cases"]
    },
    {
      "topic_name": "Knowledge Retrieval",
      "reasoning_type": "hybrid",
      "description": "Searches knowledge base deterministically by category, then uses LLM
        to summarize and rank results for relevance to the specific case",
      "actions_needed": ["Search Knowledge__kav", "Summarize articles"]
    },
    {
      "topic_name": "Escalation",
      "reasoning_type": "deterministic",
      "description": "Routes to human agent based on case classification, failed resolution
        attempts, and customer tier",
      "actions_needed": ["Create escalation record", "Route to queue"]
    }
  ],
  "replaces": [
    {"process_name": "Ticket Triage", "steps_replaced": ["Read Description", "Classify", "Assign Priority"], "replacement_type": "full"},
    {"process_name": "Knowledge Search", "steps_replaced": ["Search KB", "Evaluate Results"], "replacement_type": "full"},
    {"process_name": "Escalation Routing", "steps_replaced": ["Determine Escalation Path", "Route to Team"], "replacement_type": "partial"}
  ],
  "trigger": "Support rep opens a new Case",
  "data_requirements": ["Case", "Knowledge__kav", "Contact", "Entitlement"],
  "integration_points": [],
  "complexity_estimate": "medium",
  "confidence": 0.80,
  "rationale": "All four processes serve the same actor (support rep) working the same
    record (Case). The triage->search->resolve->escalate flow is a natural conversation
    that an agent can orchestrate as topics.",
  "risks": "Knowledge base quality directly limits resolution accuracy. If KB articles
    are outdated or sparse, the agent will escalate most cases, reducing value."
}
```

### Knowledge Reference Maintenance

The capability model, design principles, antipatterns, and examples are stored in the prompt store (`seeds.py`) as prompt blocks for the `agent_opportunity` operation. They are version-controlled and can be updated based on output quality observations without code changes to the pipeline.

---

## Phase 3: Cross-Domain Synthesis

**Module:** `backend/app/services/recommendations/cross_domain.py`

Replaces the synthesis logic currently in `candidate_generator.generate_synthesized_candidates`.

### When to Run

Only runs when the org has 2+ domains with agent opportunities. Skipped for single-domain orgs or when Phase 2 produces no opportunities.

### Input

- Summaries of all agent opportunities from Phase 2 (agent_name, description, topics, actors_impacted, data_requirements, integration_points — not the full domain context)
- Cross-domain `ProcessHandoff` records (handoffs where source and target processes belong to different domains)

### What It Looks For

1. **Cross-domain agents:** The same actor/role appears in agent opportunities across different domains doing similar work. Example: "Sales Manager" does approval work in both "Sales Operations" and "Customer Success" — a single "Approval Agent" could span both.

2. **Handoff bridge agents:** Cross-domain handoff gaps where an agent could bridge the boundary. Example: the handoff from "Sales Ops > Contract Generation" to "Legal > Contract Review" is manual and has a gap — a "Contract Processing Agent" could own the handoff.

3. **Merge candidates:** Two agent opportunities in different domains that are similar enough to be one agent. Example: "Support Triage Agent" in Customer Support and "Ticket Classification Agent" in IT Support are essentially the same agent with different data.

### Output

Same opportunity card structure as Phase 2, with `recommendation_type = "cross_domain"`. The `replaces` array spans multiple domains.

### Operation Config

```python
"agent_opportunity_cross_domain": {
    "model": "anthropic/claude-sonnet-4-6",
    "tier": "strong",
    "thinking_budget": 8000,
    "output_format": "json",
    "label": "Cross-Domain Agent Synthesis",
    "group": "synthesis",
    "description": "Identifies agent opportunities spanning multiple business domains.",
}
```

---

## Phase 4: Async Financial Evaluation

**Task:** `evaluate_agent_financials` (new Celery task)

Enqueued after Phase 2 + Phase 3 opportunities are persisted. Runs independently — does not block the main pipeline response.

### Process

For each `Recommendation` row with `financial_evaluation_status = "pending"`:

1. Read `agent_opportunity_json.financial_signals`
2. Assemble `assumptions_json` using the same industry benchmarks the current pipeline uses:
   - `primary_role_type` -> salary lookup (same `_RECOMMENDATIONS_INSTRUCTIONS` benchmarks)
   - `estimated_hours_per_week_saved` -> `hours_per_week`
   - `estimated_actor_count` -> `actor_count`
   - `estimated_frequency` -> `frequency`
   - `complexity_estimate` -> `technology_cost` estimate (low: $8k, medium: $18k, high: $35k)
   - `integration_points` count -> adjustment to `technology_cost` (+$5k per integration)
   - Agent type defaults: `change_management_factor` = 0.35, `annual_operational_cost` based on frequency and actor count, `adoption_ramp` = [0.1, 0.5, 0.85, 0.95, 1.0]
3. Run `compute_projections(assumptions)` — the existing financial engine, unchanged
4. Write back `assumptions_json`, `scenarios_json`, `estimated_roi`, `financial_evaluation_status = "completed"`

### Why Async

- Agent opportunity identification is the high-value, user-facing result. It should return fast.
- Financial projections are secondary and based on rough estimates anyway. They refine over time via chat enrichment.
- Decoupling means the pipeline doesn't fail if financial estimation has issues.
- The UI can show opportunity cards immediately and progressively enhance with financial data.

### Financial Engine

`backend/app/services/recommendations/financial_engine.py` is preserved unchanged. It's a pure function — `compute_projections(assumptions, automation_type)` -> `scenarios_json`. The 5-year NPV, J-curve, hard/soft savings split, and sensitivity analysis all still apply to agent opportunities.

---

## Data Model Changes

### Migration: New columns on `Recommendation`

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `agent_opportunity_json` | `JSONB` | `{}` | Full agent opportunity card (topics, replaces, trigger, data_requirements, etc.) |
| `linked_step_ids` | `JSONB` | `[]` | Step-level UUIDs the opportunity replaces (more granular than `linked_process_ids`) |
| `domain_id` | `UUID` FK -> business_processes | nullable | The domain this opportunity belongs to (null for cross-domain) |
| `financial_evaluation_status` | `String(20)` | `'pending'` | `pending` / `completed` / `failed` |

### Modified field semantics

| Column | Old Usage | New Usage |
|--------|-----------|-----------|
| `recommendation_type` | `discovered` / `synthesized` | `agent_opportunity` / `cross_domain` |
| `automation_type` | `deterministic` / `agentic` / `hybrid` | Derived from the mix of `reasoning_type` values across the opportunity's topics. Kept for API compatibility. |
| `composite_score` | `base_score * 0.7 + llm_score * 0.3` | LLM-provided `confidence` score (0-1). No heuristic blend. |
| `linked_process_ids` | Single process ID (discovered) or multi-process (synthesized) | All process IDs the agent opportunity covers |
| `analysis_inputs_json` | Heuristic signals | Domain context summary (domain name, process count, step count) |

### Removed concepts

These columns remain on the model for backward compatibility but are no longer populated by the new pipeline:

- `base_score` — no heuristic scoring layer
- `llm_score` — replaced by `confidence` in `agent_opportunity_json`
- `score_divergence_flag` — no dual-score system
- `llm_rationale` — replaced by `rationale` and `description` in `agent_opportunity_json`

### `agent_opportunity_json` schema

Mirrors the Phase 2 output protocol. Stored as-is from the LLM response after ID resolution.

```json
{
    "agent_name": "Order Fulfillment Agent",
    "agent_type": "headless",
    "description": "...",
    "topics": [
        {
            "topic_name": "Order Validation",
            "description": "...",
            "reasoning_type": "deterministic",
            "actions_needed": ["..."]
        }
    ],
    "replaces": [
        {
            "process_id": "uuid",
            "process_name": "Order Validation",
            "steps_replaced": ["Field Check", "Payment Verify"],
            "step_ids": ["uuid", "uuid"],
            "replacement_type": "full"
        }
    ],
    "trigger": "Order.Status changed to 'Submitted'",
    "data_requirements": ["Order", "OrderItem"],
    "integration_points": ["Shipping carrier API"],
    "complexity_estimate": "medium",
    "confidence": 0.85,
    "rationale": "...",
    "risks": "...",
    "financial_signals": {
        "actors_impacted": ["Fulfillment Coordinator"],
        "estimated_hours_per_week_saved": 12.5,
        "estimated_frequency": "daily",
        "estimated_actor_count": 4,
        "primary_role_type": "operations"
    }
}
```

---

## Pipeline Orchestration

**Entry point:** `run_recommendation_pipeline` in `pipeline.py` (rewritten)

```
async def run_recommendation_pipeline(org_id, db, existing_run_id=None):
    1. Create/reuse RecommendationRun, set status = "running"

    2. Phase 1: Domain Context Assembly
       - Get latest completed DiscoveryRun
       - For each domain: assemble DomainContext
       - Store timing in stage_results

    3. Phase 2: Agent Opportunity Analysis
       - For each domain: call agent_analyzer with DomainContext + knowledge ref
       - Resolve IDs from LLM output
       - Collect all opportunities
       - Store timing + counts in stage_results

    4. Phase 3: Cross-Domain Synthesis (if 2+ domains with opportunities)
       - Call cross_domain analyzer with opportunity summaries + cross-domain handoffs
       - Resolve IDs, collect additional opportunities
       - Store timing in stage_results

    5. Persist
       - Delete previous pipeline-generated recommendations (same logic as current)
       - Create Recommendation rows from all opportunities
       - Set financial_evaluation_status = "pending"
       - Update RecommendationRun status = "completed"

    6. Enqueue Phase 4
       - Celery task: evaluate_agent_financials(org_id, run_id)
```

Cancellation and heartbeat logic carry over from the current pipeline.

---

## Chat Enrichment

The existing chat enrichment flow adapts to agent opportunities:

### Anchor context changes

When `anchor_type == "recommendation"` and the recommendation is an `agent_opportunity`:

- System prompt includes: agent name, description, topics (with reasoning types), processes/steps replaced, trigger, data requirements, integration points, complexity, confidence, risks
- Financial context (when available): assumptions, projections, hard/soft split — same as current
- Role instruction updated: focus on evaluating the agent opportunity — is the scope right? Are the topics correct? Are there missing integration points? Then refine financial assumptions.

### Chat tools

Existing tools carry over:
- `get_recommendation_details` — updated to include `agent_opportunity_json`
- `get_process_context` — unchanged, shows linked process enrichment
- `update_assumption` — unchanged, updates financial assumptions

No new tools needed for v1. Future enhancement: a `refine_opportunity` tool that lets the user adjust agent boundaries (add/remove topics, change scope) via chat.

---

## API Changes

### Modified endpoints

| Method | Path | Change |
|--------|------|--------|
| `GET` | `/recommendations/` | New filter: `recommendation_type` supports `agent_opportunity` and `cross_domain`. New sort option: `confidence`. |
| `GET` | `/recommendations/{id}` | Response includes `agent_opportunity_json`, `linked_step_ids`, `domain_id`, `financial_evaluation_status` |
| `GET` | `/recommendations/summary` | Updated to group by agent_type (headless/conversational/hybrid) instead of automation_type |

### Unchanged endpoints

- `POST /recommendations/generate` — triggers the new pipeline (same API contract)
- `POST /recommendations/{id}/recalculate` — works with agent opportunities (same financial engine)
- `POST /recommendations/portfolio-projection` — aggregation works the same way
- `GET /recommendations/status` — run status polling unchanged
- `PATCH /recommendations/{id}/status` — status transitions unchanged

---

## File-Level Impact

### New files

| File | Purpose |
|------|---------|
| `backend/app/services/recommendations/domain_assembler.py` | Phase 1: domain context assembly |
| `backend/app/services/recommendations/agent_analyzer.py` | Phase 2: LLM agent opportunity analysis |
| `backend/app/services/recommendations/cross_domain.py` | Phase 3: cross-domain synthesis |
| New Alembic migration | Add columns to `recommendations` table |

### Rewritten files

| File | Change |
|------|--------|
| `backend/app/services/recommendations/pipeline.py` | New 4-phase orchestration replacing the current 4-stage pipeline |
| `backend/app/services/prompts/seeds.py` | New prompt blocks: `_AGENT_OPPORTUNITY_*`, `_AGENT_OPPORTUNITY_CROSS_DOMAIN_*` |
| `backend/app/services/ai/operations.py` | New operation configs: `agent_opportunity`, `agent_opportunity_cross_domain` |
| `backend/app/models/recommendation.py` | New columns |
| `backend/app/schemas/recommendation.py` | Updated response schema |
| `backend/app/api/routes/recommendations.py` | Updated filters, sorts, response fields |
| `backend/app/workers/analysis.py` | New Celery task `evaluate_agent_financials` |

### Deprecated files (delete after migration)

| File | Reason |
|------|--------|
| `backend/app/services/recommendations/heuristic_scorer.py` | No heuristic scoring in new pipeline |
| `backend/app/services/recommendations/candidate_generator.py` | Replaced by `domain_assembler.py` |
| `backend/app/services/recommendations/llm_scorer.py` | Replaced by `agent_analyzer.py` |

### Preserved unchanged

| File | Reason |
|------|--------|
| `backend/app/services/recommendations/financial_engine.py` | Pure math, still correct |
| `backend/app/services/recommendations/roi.py` | Helper, still useful |
| `backend/app/services/chat/context.py` | Adapted but same architecture |
| `backend/app/services/chat/tools/recommendation_tools.py` | Same tools, updated payloads |
| Frontend components | Updated data display, same architecture |

---

## Antipatterns to Watch

### 1. The Mega-Agent Trap

**Risk:** The LLM proposes one agent per domain that replaces everything. This is unusable — too broad to implement, too complex to maintain.

**Mitigation:** The antipatterns section in the knowledge reference explicitly addresses this. The design principles state 3-6 topics per agent. If the LLM returns an agent with 10+ topics, the pipeline should log a warning and still persist it, but flag it for review.

### 2. The Process-Step Agent (What We're Trying to Avoid)

**Risk:** Despite instructions, the LLM falls back to one agent per process.

**Mitigation:** The knowledge reference, antipatterns, AND worked examples all reinforce the cross-process pattern. Post-processing validation: if a returned agent opportunity only replaces steps from a single process AND that process has fewer than 4 steps, flag it as potentially too narrow.

### 3. Hallucinated Capabilities

**Risk:** The LLM proposes an agent that uses capabilities Agentforce doesn't have (e.g., direct database writes without Apex, real-time streaming, multi-session state).

**Mitigation:** The capability model explicitly lists what agents CANNOT do. Post-processing can check `integration_points` and `actions_needed` against known capability constraints.

### 4. Financial Signal Garbage

**Risk:** The `financial_signals` the LLM embeds are wildly inaccurate (e.g., 100 hours/week saved for a weekly process with 2 actors).

**Mitigation:** The async financial evaluation (Phase 4) can apply sanity bounds: hours_per_week_saved capped at `actor_count * 40`, frequency alignment checks, etc. Bad signals produce bad NPV, but chat enrichment can fix it.

### 5. Cross-Domain Duplication

**Risk:** Phase 2 proposes similar agents in two domains, and Phase 3 fails to merge them, resulting in overlapping recommendations.

**Mitigation:** Phase 3's explicit mandate includes finding merge candidates. Post-processing: check for opportunities with >50% overlap in `linked_process_ids` and flag for review.

---

## Research Flag: Agentforce Knowledge Grounding

The knowledge reference (Section 7 of this spec) represents the initial approach. Areas flagged for iteration:

1. **Capability model completeness** — Monitor Phase 2 output for cases where the LLM proposes infeasible agents. Each case indicates a missing capability constraint. Update the capability model accordingly.

2. **Example calibration** — The two worked examples set a quality bar. If output quality is inconsistent, add a third example covering a different pattern (e.g., a hybrid agent with both conversational and headless topics). More than 3 examples risks over-constraining the LLM's creativity.

3. **Org-specific context** — Future enhancement: inject information about agents the org already has deployed, so the engine doesn't recommend duplicating existing automation. This would come from the `Agent` model.

4. **Token budget monitoring** — Track actual token consumption per Phase 2 call. If large domains consistently approach context limits, the truncation strategy in Phase 1 needs refinement.

---

## Out of Scope (Future Work)

- **AgentScript generation** — Taking an accepted agent opportunity and generating draft Agent Script. The `agent_opportunity_json` contains enough structure (topics, actions, trigger, data_requirements) to seed this, but it's a separate pipeline.
- **Agent deployment tracking** — Connecting deployed Agentforce agents back to their source recommendations for measuring actual vs. projected value.
- **Incremental re-analysis** — Re-running the engine when discovery data changes and only updating affected opportunities.
- **Coverage visualization** — A domain map view showing which processes/steps are covered by agent opportunities and which aren't.
- **Multi-org synthesis** — Identifying agent patterns that could be shared across orgs (relevant for consulting/SI use cases).
