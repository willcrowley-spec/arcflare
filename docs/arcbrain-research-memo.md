# Arcbrain Research Memo

Date: 2026-05-16

## Executive Answer

Arcbrain is worth pursuing, but only if it is treated as a first-class product primitive, not as a cool 3D metadata viewer.

GitNexus proves that graph-native exploration can make complex systems feel understandable. Its strongest ideas are local graph indexing, freshness awareness, graph chat, impact analysis, cluster summaries, and search-to-highlight navigation. Arcflare should not use GitNexus code, package structure, UI, assets, or product language. The public GitNexus repo is licensed under PolyForm Noncommercial, and its README points commercial users to separate licensing. The safe path is clean-room: study public behavior, then build an Arcflare-native operating graph around Salesforce metadata, process intelligence, evidence, economics, replacement decisions, and agent design packages.

The strategic distinction is simple:

- GitNexus visualizes a codebase brain.
- Arcbrain visualizes a company's operating brain.

That distinction matters. A code graph can tell an engineer what code depends on what. Arcbrain should tell an executive what work depends on what systems, people, controls, documents, manual handoffs, and economics - and what can be replaced safely.

## Sources Reviewed

External sources:

- [GitNexus README](https://raw.githubusercontent.com/abhigyanpatwari/GitNexus/main/README.md)
- [GitNexus license](https://raw.githubusercontent.com/abhigyanpatwari/GitNexus/main/LICENSE)
- [GitNexus multi-repo documentation](https://abhigyanpatwari-gitnexus.mintlify.app/mcp/multi-repo)
- [Celonis Process Intelligence Graph](https://docs.celonis.com/en/process-intelligence-graph.html)
- [Microsoft Power Automate process map overview](https://learn.microsoft.com/en-us/power-automate/minit/process-map)
- [UiPath Task Mining](https://www.uipath.com/product/task-mining)
- [Neo4j Bloom user guide](https://neo4j.com/docs/bloom-user-guide/current/)
- [Microsoft GraphRAG paper](https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/)
- [Anthropic, Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Salesforce Agentforce hybrid reasoning](https://architect.salesforce.com/docs/architect/fundamentals/guide/hybrid-reasoning-agentforce-builder-agent-script)
- [NIST AI 600-1, Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [OWASP Agentic AI threats and mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Sigma.js rendering documentation](https://v4.sigmajs.org/concepts/rendering/)
- [Three.js fundamentals](https://threejs.org/manual/en/fundamentals.html)
- [3d-force-graph package documentation](https://www.npmjs.com/package/3d-force-graph)

Local Arcflare sources:

- [README.md](../README.md)
- [backend/app/models/metadata.py](../backend/app/models/metadata.py)
- [backend/app/models/process.py](../backend/app/models/process.py)
- [backend/app/models/knowledge.py](../backend/app/models/knowledge.py)
- [backend/app/models/recommendation.py](../backend/app/models/recommendation.py)
- [backend/app/services/metadata_graph.py](../backend/app/services/metadata_graph.py)
- [backend/app/services/metadata_vectorizer.py](../backend/app/services/metadata_vectorizer.py)
- [backend/app/services/processes/domain_graph.py](../backend/app/services/processes/domain_graph.py)
- [frontend/package.json](../frontend/package.json)
- [frontend/src/pages/Processes/DomainMap.tsx](../frontend/src/pages/Processes/DomainMap.tsx)
- [frontend/src/lib/elkLayout.ts](../frontend/src/lib/elkLayout.ts)

## 1. GitNexus Capability Benchmark

GitNexus should be treated as competitive inspiration, not an implementation source.

Publicly visible capabilities worth learning from:

| Capability | What GitNexus appears to do | Arcbrain clean-room equivalent |
| --- | --- | --- |
| Graph index | Indexes code into nodes, edges, clusters, flows, and embeddings | Build an org graph from Salesforce metadata, documents, processes, telemetry, recommendations, and replacement decisions |
| Local/private mode | Emphasizes local or in-browser processing for privacy | Keep customer org data tenant-scoped, permission-aware, and exportable without exposing raw evidence unnecessarily |
| Freshness/staleness | Tracks whether an index is stale relative to repo changes | Track sync freshness, source artifact versions, evidence age, org metadata drift, and plan staleness |
| Graph chat | Lets users ask questions over graph context | Arcbrain investigator answers questions with cited nodes, edges, assumptions, and confidence |
| Impact analysis | Shows blast radius of code or dependency changes | Show blast radius of replacing a role, process, object, Flow, permission, integration, or manual handoff |
| Cluster summaries | Groups related areas into functional communities | Summarize business domains, process communities, automation clusters, evidence communities, and replacement zones |
| Search-to-highlight | Search finds and focuses related nodes | Search for process, object, team, cost center, recommendation, blocker, evidence claim, or agent action and light up the connected path |
| Multi-repo concept | Organizes multiple codebases into a larger system view | Organize multiple org sources: Salesforce orgs, docs, tickets, Slack/Teams, ERP, data warehouse, and identity data |
| Agent context tools | Gives AI agents structured context instead of loose text | Give Arc, replacement planners, and future agent compilers graph tools grounded in evidence and permissions |

Capabilities to avoid copying:

- Source code, package structure, generated files, CLI commands, MCP tool names, UI components, icons, screenshots, visual layout, assets, slogans, and product metaphors.
- Their exact storage and indexing stack. Arcflare already has PostgreSQL, pgvector, metadata dependencies, communities, and process graph assets.
- Their code-oriented graph schema. Arcbrain needs an operating-model schema, not file/symbol/process-code schema.
- The idea that visualization alone is the product. For Arcflare, the graph is valuable only when it supports replacement decisions.

License posture:

- GitNexus is not an acceptable dependency for Arcflare commercial use without separate licensing.
- Public product behavior can inform competitive analysis.
- Implementation should be clean-room and Arcflare-native.
- If future work requires direct comparison screenshots or source inspection, that should be treated as legal/product review work, not implementation input.

## 2. Arcbrain Product Thesis

Arcbrain should be the explorable, evidence-backed digital representation of how a customer's operating model actually works.

The current Arcflare product already has the raw ingredients:

- Salesforce metadata objects, fields, automations, components, dependencies, record telemetry, and licensing signals.
- Business process hierarchy, actors, artifacts, trigger conditions, decision logic, touchpoints, success criteria, failure modes, sequencing, confidence, and evidence sources.
- Document-derived concepts, concept co-occurrences, communities, chunk links, and vectorized knowledge.
- Recommendations with linked processes, linked steps, agent opportunity JSON, ARC score JSON, financial assumptions, and scenarios.
- A React Flow and ELK-based process map surface.

The missing layer is a unified Arcbrain graph that treats those assets as one operating system:

```text
Source artifacts
  -> Evidence claims
  -> Evidence / metadata / process / replacement graph
  -> Arcbrain views and lenses
  -> Executive questions
  -> Replacement plan and agent design packages
```

Arcbrain's job is not to show every metadata item. That would become visual noise. Its job is to let an executive ask:

- What manual work exists here?
- Which work is rule-based, judgment-based, or relationship-sensitive?
- Which teams and processes depend on this object, Flow, integration, document, queue, or approval?
- If we remove this role or process step, what breaks?
- What replacement architecture is safest?
- What savings are hard savings versus soft productivity?
- What evidence supports the plan?
- What is missing before we should trust the answer?

That is more valuable than a graph viewer. It is a decision instrument.

## 3. Arcbrain Graph Model

Arcbrain should introduce a graph projection layer before any 3D renderer. The renderer must not define the domain model.

Recommended graph primitives:

### ArcbrainNode

Minimum fields:

- `id`
- `org_id`
- `snapshot_id`
- `node_type`
- `source_type`
- `source_ref`
- `label`
- `summary`
- `layer`
- `community_id`
- `confidence`
- `freshness`
- `risk_level`
- `replaceability_score`
- `economic_value`
- `evidence_refs`
- `metrics_json`
- `metadata_json`

Initial node types:

- `metadata_object`
- `metadata_field`
- `automation`
- `apex_class`
- `permission`
- `package`
- `document`
- `document_chunk`
- `evidence_claim`
- `business_domain`
- `business_process`
- `process_step`
- `actor`
- `team`
- `handoff`
- `control`
- `system`
- `integration`
- `recommendation`
- `replacement_decision`
- `agent_action`
- `agent_design_package`
- `risk`
- `metric`
- `assumption`
- `blocker`

### ArcbrainEdge

Minimum fields:

- `id`
- `org_id`
- `snapshot_id`
- `source_node_id`
- `target_node_id`
- `edge_type`
- `direction`
- `weight`
- `confidence`
- `evidence_refs`
- `metrics_json`
- `metadata_json`

Initial edge types:

- `depends_on`
- `reads`
- `writes`
- `triggers`
- `calls`
- `validates`
- `uses_system`
- `performed_by`
- `owned_by`
- `hands_off_to`
- `governed_by`
- `supported_by_evidence`
- `contradicted_by_evidence`
- `replaces`
- `blocks`
- `requires_permission`
- `drives_metric`
- `saves_cost`
- `increases_risk`
- `part_of`
- `similar_to`
- `same_as`

### ArcbrainSnapshot

Immutable graph projection generated from one investigation run.

Fields:

- `id`
- `org_id`
- `created_at`
- `source_artifact_ids`
- `metadata_sync_id`
- `discovery_run_id`
- `recommendation_run_id`
- `replacement_plan_id`
- `graph_version`
- `node_count`
- `edge_count`
- `staleness_status`
- `projection_status`
- `summary_json`

### ArcbrainView

Saved graph perspective, not raw graph data.

Examples:

- `executive_constellation`
- `metadata_dependency`
- `replacement_heat`
- `trust_lens`
- `blast_radius`
- `process_path`
- `agent_design`

Fields:

- selected node/edge types
- layout mode
- filters
- color semantics
- focus node
- camera/viewport state
- visible depth
- aggregation thresholds
- collapsed communities

### ArcbrainQueryResult

The response contract for graph chat and search.

Fields:

- `answer`
- `answer_type`
- `confidence`
- `nodes`
- `edges`
- `paths`
- `supporting_claims`
- `assumptions`
- `missing_evidence`
- `recommended_view`
- `suggested_next_questions`

This keeps Arc chat grounded. The assistant should not just answer; it should return what to highlight.

## 4. What Should Be 3D, 2D, And Textual

The 3D view should be powerful, but it should not carry precision work.

### Use 3D for executive sensemaking

Best use cases:

- Constellation view of the customer's operating brain.
- Replacement heat map across domains.
- Blast-radius exploration for "what happens if we remove this work?"
- Evidence path animation from question to answer.
- Boardroom storytelling: before-state, target-state, replacement sequence.

Why 3D works here:

- Executives do not need to edit every graph edge.
- 3D makes complexity feel tangible.
- It supports "talking to the brain of the org" without pretending every node is equally important.
- It can create the first emotional hook while the side panels carry the proof.

### Use 2D for analysis and precision

Best use cases:

- Process maps.
- Handoffs.
- approval flows.
- object dependency maps.
- agent action sequence diagrams.
- deterministic versus agentic boundary review.

Arcflare already has React Flow and ELK for this. Keep using them.

### Use tables/text for trust and decisions

Best use cases:

- Replacement plan.
- financial model.
- risks and blockers.
- assumptions.
- source citations.
- permission checks.
- eval results.
- approval record.

Executives may like the brain view. They will trust the plan because the side panel proves every claim.

## 5. UX Concept Brief

Arcbrain should feel like an executive intelligence instrument, not a sci-fi demo.

Visual direction:

- Light Arcflare shell.
- Dark navy graph canvas only where the 3D scene needs contrast.
- Orange for focus, active path, and executive action.
- Semantic colors only for status: green for validated, amber for assumption/missing evidence, red for blocked/high risk.
- No purple-blue neon, generic glows, bokeh, glass cards, or decorative particle excess.
- Dense side panels with real operational data.

Primary views:

### 1. Arcbrain Overview

Shows the org as clustered domains:

- Sales
- service
- finance
- operations
- platform architecture
- documents/evidence
- automations
- replacement opportunities

Each cluster shows:

- confidence
- evidence coverage
- replacement value
- risk density
- staleness
- manual work density

### 2. Ask The Brain

Executive asks a question. Arcbrain returns:

- answer
- highlighted graph path
- supporting evidence
- assumptions
- missing evidence
- recommended replacement decisions

Example question:

```text
What work can we remove in support operations without increasing customer risk?
```

The graph should light up:

```text
Cases -> queues -> handoffs -> macros/flows -> SOP documents -> agents -> controls -> savings
```

### 3. Blast Radius

Select a process, role, object, Flow, integration, permission set, or replacement decision.

Arcbrain answers:

- upstream dependencies
- downstream dependencies
- affected processes
- affected teams
- financial impact
- risk impact
- evidence confidence
- automation/replacement alternatives

### 4. Replacement Heat

Graph lens by replaceability:

- high-value safe replacement
- high-value but blocked
- deterministic automation
- agentic automation
- augment only
- do not replace
- insufficient evidence

This is where Arcbrain connects directly to the replacement platform strategy.

### 5. Trust Lens

Toggle node/edge visibility by epistemic status:

- observed fact
- inferred claim
- assumption
- contradiction
- stale evidence
- missing evidence
- validated by eval

This is the anti-gimmick layer. The visual brain becomes credible because it shows uncertainty.

### 6. Agent Design Lens

For an approved replacement decision, show:

- proposed agent/subagent
- deterministic steps
- LLM reasoning zones
- required actions
- permissions
- systems touched
- test scenarios
- rollback path
- observability requirements

This aligns with Salesforce's hybrid reasoning direction: deterministic logic where reproducibility matters, LLM reasoning only where judgment is needed.

## 6. Technical Architecture Recommendation

Do not create a separate repo yet.

Build Arcbrain inside the current Arcflare app as a bounded backend and frontend module. Split later only if it becomes an embeddable SDK or standalone product.

Recommended boundaries:

```text
backend/app/services/arcbrain/
  projection.py
  scoring.py
  query.py
  layout.py
  summarizer.py
  schemas.py

backend/app/api/routes/arcbrain.py

frontend/src/features/arcbrain/
  api/
  components/
  graph/
  lenses/
  pages/
  state/
  types.ts
```

Architecture principles:

- The backend owns graph projection, scoring, source lineage, staleness, and query results.
- The frontend owns rendering, interaction, camera state, panels, and view presets.
- The renderer consumes a stable Arcbrain graph contract.
- Do not bind the domain model to Three.js, Sigma.js, or React Flow.
- Build multiple renderers against the same graph contract.

Renderer recommendation:

| Surface | Recommended renderer | Reason |
| --- | --- | --- |
| precise process maps | existing React Flow + ELK | Already in repo and good for editable 2D diagrams |
| large 2D graph | Sigma.js/WebGL | Purpose-built for large interactive graphs |
| executive 3D brain | Three.js or React Three Fiber | Gives custom scene control and brandable visual language |
| quick prototype | 3d-force-graph | Fastest proof of 3D interaction, but should be treated as replaceable |

The first prototype can use `3d-force-graph` or a thin Three.js scene if speed matters. The production direction should likely be a custom Three.js or React Three Fiber renderer because Arcbrain needs branded interaction, side-panel integration, performance controls, reduced motion, and domain-specific lenses.

Performance design:

- Never render the raw graph by default.
- Pre-aggregate by community.
- Use level-of-detail thresholds.
- Render top N high-signal nodes first.
- Load neighbors on expand.
- Cap visible edges by lens.
- Keep layout computation outside the render loop.
- Cache layout positions per snapshot and view.
- Provide 2D/table fallback for accessibility and low-power devices.

## 7. Competitive Landscape

### GitNexus and code graph tools

Strength:

- Great mental model for "system brain" exploration.
- Strong agent context story.
- Useful concepts around staleness, impact, cluster summaries, and graph chat.

Gap Arcbrain can exploit:

- Code comprehension is not operating-model replacement.
- Does not combine business processes, Salesforce metadata, documents, economics, controls, and replacement plans.

### Celonis

Strength:

- Celonis has the strongest public articulation of process intelligence as an operating graph. Its Process Intelligence Graph is explicitly cross-system, object-centric, and intended as a foundation for automation and AI.

Gap Arcbrain can exploit:

- Celonis is process intelligence first. Arcbrain should be Salesforce operating-model replacement first.
- Arcbrain can bias toward "what human work can be removed and what agent/design package replaces it?"
- Arcbrain can be lighter-weight for Salesforce-heavy enterprises and sharper around metadata, Agentforce, permissions, and implementation design packages.

### UiPath

Strength:

- Strong task/process mining and automation pipeline framing.
- Good at desktop task capture and RPA opportunity identification.

Gap Arcbrain can exploit:

- UiPath centers automation/RPA execution. Arcbrain should center executive replacement decisions and evidence-backed operating-model redesign.
- Arcbrain should decide between deterministic automation, agentic automation, workflow redesign, tool retirement, and "do not replace."

### Microsoft Process Mining

Strength:

- Clear process maps with activities, transitions, metrics, clustering, hierarchical maps, and exports.

Gap Arcbrain can exploit:

- Microsoft process maps show behavior captured in event data. Arcbrain should connect behavior to Salesforce configuration, documents, permissions, replacement economics, and agent design.

### Neo4j Bloom

Strength:

- Business-friendly graph exploration.
- Strong "graph for non-graph users" framing.

Gap Arcbrain can exploit:

- Bloom is a general graph exploration product. Arcbrain should be opinionated around AI work replacement and executive trust.

### Glean and enterprise search/work graphs

Strength:

- Cross-system search, permissions, knowledge graph, assistant access to enterprise content.

Gap Arcbrain can exploit:

- Enterprise search answers "what do we know?"
- Arcbrain answers "what work can we remove, what replaces it, what proof supports that, and what is blocked?"

### Salesforce Agentforce

Strength:

- Agentforce is the natural runtime target for Salesforce-heavy customers.
- Agent Script's deterministic/LLM split is the right design direction.

Gap Arcbrain can exploit:

- Agentforce helps build agents. It does not deeply inspect a customer's full operating model and produce a replacement plan before the build.
- Arcbrain should become the pre-Agentforce intelligence and design layer.

### GraphRAG and agentic BPM research

Strength:

- GraphRAG validates graph-based sensemaking over private corpora, especially for global questions.
- Agentic BPM research validates the need to frame agents inside process structures.

Gap Arcbrain can exploit:

- Most research is architecture or technique. Arcbrain can productize the executive workflow: evidence, graph, replacement plan, design package, eval, runtime export.

## 8. Is This Novel Enough?

The individual ingredients are not novel:

- graph visualization exists.
- process mining exists.
- task mining exists.
- enterprise search exists.
- GraphRAG exists.
- Salesforce metadata analysis exists.
- AI agents exist.

The combination is where Arcbrain can be meaningfully different:

```text
Salesforce metadata intelligence
+ business process discovery
+ document/evidence graph
+ economic replacement modeling
+ role/process impact analysis
+ permission/control validation
+ agent design package generation
+ executive 3D investigation surface
= Arcbrain
```

The differentiator is not the 3D scene. The differentiator is that the 3D scene is a live projection of a governed replacement-decision graph.

Credible claim:

Arcbrain can be positioned as an "enterprise operating brain for AI work replacement planning" if it can prove:

- every visual node has source lineage.
- every recommendation has evidence and confidence.
- every replacement decision has economics and risk.
- every agent design package has permissions, tests, observability, and rollback.
- every answer can show what is known, inferred, assumed, stale, or missing.

That would be modern and differentiated. It is not "never-before-been-done" in the sense that no one has ever visualized a graph. It may be novel as a Salesforce-centered executive work-replacement graph that connects metadata, process intelligence, evidence, economics, and agent implementation design.

That is the positioning to use. It is ambitious without being fake.

## 9. Prototype Plan

Goal: prove the wow without compromising the foundation.

### Prototype 1: Arcbrain Graph Projection

Build a backend endpoint that projects existing Arcflare data into a normalized graph.

Inputs:

- `MetadataObject`
- `MetadataField`
- `MetadataAutomation`
- `MetadataComponent`
- `MetadataDependency`
- `BusinessProcess`
- `ProcessHandoff`
- `Concept`
- `Community`
- `Recommendation`

Output:

- nodes
- edges
- communities
- metrics summary
- stale/missing evidence flags

Do not add the full SourceArtifact model in the prototype unless the broader replacement-platform foundation is being implemented at the same time. For the prototype, preserve source refs and confidence fields so the contract can evolve.

### Prototype 2: Arcbrain Executive Constellation

Build a new frontend Arcbrain page with:

- 3D graph canvas.
- left investigation/search rail.
- right trust/details panel.
- top lens switcher.
- selected node detail.
- path highlight.
- graph stats and staleness.

Initial lenses:

- Overview.
- Replacement Heat.
- Blast Radius.
- Trust.

### Prototype 3: Ask The Brain Mock-Real Query

Implement graph query templates before fully agentic chat.

Queries:

- "What can we replace?"
- "Why is this process risky?"
- "What depends on this object?"
- "What manual handoffs exist in this domain?"
- "What evidence supports this recommendation?"

Each query should return:

- answer text.
- highlighted nodes.
- highlighted edges.
- assumptions.
- missing evidence.
- next investigation step.

This avoids building a vague chatbot first.

### Prototype 4: Blast Radius And Replacement Heat

Make these interactions feel undeniable:

- Select a role/process/object/Flow.
- Show connected process dependencies.
- Show replacement candidates.
- Show financial upside.
- Show blockers.
- Show risk.

This is the product moment: the executive sees that Arcbrain understands the operating model, not just the metadata.

### Prototype 5: Agent Design Preview

For one recommendation, show a prototype Agent Design Package:

- deterministic steps.
- LLM reasoning zones.
- required Salesforce actions.
- permission requirements.
- test scenarios.
- rollback path.

This makes Arcbrain point forward to implementation, not stop at visualization.

## 10. Risks And Controls

| Risk | Why it matters | Control |
| --- | --- | --- |
| GitNexus licensing contamination | Commercial use risk and avoidable distraction | Public capability benchmark only; no code, UI, assets, schema, or product language reuse |
| 3D gimmick risk | Executives may be impressed once, then stop trusting it | Tie every visual interaction to evidence, economics, risk, and replacement decisions |
| Graph clutter | Enterprise graphs become unreadable fast | Community aggregation, lens filters, level-of-detail, top-N ranking, neighbor expansion |
| Performance | Large orgs can produce thousands of metadata/process/evidence nodes | Precompute snapshots, cache layouts, use WebGL, cap visible graph, avoid raw graph default |
| False confidence | A beautiful graph can make weak evidence feel stronger than it is | Trust Lens, confidence bands, stale flags, assumptions, missing evidence, citation drawer |
| Accessibility | 3D scenes are poor primary interfaces for many users | Provide 2D graph, table, keyboard navigation, reduced motion, and textual answer equivalents |
| Data sensitivity | Org graphs expose process, security, and staffing intelligence | Tenant scoping, permission-aware APIs, source redaction, audit logging, export controls |
| Wrong abstraction | Renderer-specific model would trap the product | Stable backend graph contract with replaceable renderers |
| Runtime confusion | Users may think Arcbrain deploys agents directly | Separate investigation, recommendation, design package, eval, approval, and runtime export |
| ROI overstatement | Replacement claims can become fantasy math | Separate hard savings from soft productivity, show assumptions, avoid double counting |

## 11. Recommended Implementation Direction

Build Arcbrain as an internal bounded module in this repo.

Do not split into a separate repo yet.

Do not start with a 3D renderer.

Start with a stable graph projection contract and one generated snapshot from existing Arcflare data. Then build the 3D executive surface as one renderer over that contract.

Recommended first implementation milestone:

```text
Arcbrain V0

Backend:
- /arcbrain/snapshot
- /arcbrain/search
- /arcbrain/node/{id}
- /arcbrain/blast-radius/{id}
- /arcbrain/replacement-heat

Frontend:
- /arcbrain
- 3D constellation renderer
- lens switcher
- search rail
- trust/details drawer
- path highlight

Data:
- metadata graph
- process graph
- knowledge communities
- recommendations
- confidence and stale flags
```

Definition of "good enough" for V0:

- An executive can ask what work can be replaced and see the relevant graph regions light up.
- Selecting a node explains why it matters.
- The graph exposes evidence and missing evidence.
- Blast radius works for at least metadata objects, automations, processes, and recommendations.
- Replacement Heat shows where automation potential, savings, confidence, and risk concentrate.
- The experience feels visually distinctive but still serious enough for a CIO/COO.

## 12. Bottom Line

Arcbrain should not be "GitNexus for Salesforce." That is too small and too risky.

Arcbrain should be the visual and conversational operating model for AI work replacement.

The product should let an executive talk to the brain of their company and get an answer that is not just fluent, but inspectable:

- here is the work.
- here are the dependencies.
- here is the evidence.
- here is the replacement path.
- here are the savings.
- here are the risks.
- here is what we still do not know.

That is the version that can make Arcflare feel like category-defining software instead of another AI wrapper.
