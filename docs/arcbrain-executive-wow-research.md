# Arcbrain Executive Wow Research

Date: 2026-05-19

## Executive Answer

Arcbrain can be visually much stronger, but the fix is not to show only the code graph and it is not to show more raw nodes.

The right default is an executive semantic brain: a curated operating model with expandable source layers. Code intelligence should be present, but behind the business question. Executives should see processes, systems, teams, controls, evidence, economics, and replacement paths first. Code should appear when it explains implementation feasibility, risk, dependencies, or build plan.

The current Arcbrain view is useful as a diagnostic graph, but it still exposes too much raw structure. A 1,400-node cloud can prove that data exists, yet it does not create the feeling of "talking to the system." The "wow" moment should be:

> Ask a question, watch Arcbrain consult the operating brain, then see the specific evidence path that supports the recommendation.

## Research Takeaways

### Neo4j Bloom

Neo4j Bloom positions graph UX around codeless exploration, search-to-visualization, saved perspectives, and collaboration. The important product lesson is not the exact visual style. It is that graph novices need business-friendly perspectives and search-driven exploration, not raw graph mechanics.

Source: https://neo4j.com/product/bloom/

### Celonis Process Intelligence Graph

Celonis frames its PI Graph as a system-agnostic digital twin of business operations, enriched with KPIs, workflows, business rules, roles, and process knowledge. This is closer to Arcbrain's product wedge than a code graph is. Arcbrain should borrow the idea of a semantic business layer over system data, then differentiate around Salesforce metadata, evidence trust, replacement economics, and agent design packages.

Source: https://documentation.celonis.com/en/process-intelligence-graph.html

### Microsoft GraphRAG

GraphRAG's key idea is extracting a knowledge graph, building community hierarchy, summarizing communities, and using those structures for RAG. Arcbrain should apply that to the visual model: communities should be first-class summarized objects, not just invisible layout buckets.

Source: https://microsoft.github.io/graphrag/

### Glean Knowledge Graph

Glean's graph model is built around content, people, and activity with permissions as a core concern. Arcbrain is currently strong on metadata/process/recommendations but weaker on people/activity. For the "talk to your system" promise, Arcbrain needs to ingest or infer people, role, team, and activity context safely.

Source: https://docs.glean.com/security/knowledge-graph

### Graphistry, Sigma.js, And Cosmograph

Large graph UX needs GPU rendering, guided investigation templates, and level-of-detail. Sigma.js emphasizes WebGL rendering for large graphs. Cosmograph is explicit that large graph layout and rendering become separate performance problems. Graphistry's product language is useful: turn data into investigations, guided templates, and pivots.

Sources:

- https://www.graphistry.com/
- https://v4.sigmajs.org/concepts/rendering/
- https://cosmograph.app/docs-general/concept/

### codebase-memory-mcp

`codebase-memory-mcp` is useful as a structural code intelligence source: repos, files, classes, functions, routes, calls, and impact paths. It should not become the product's default visual ontology. Its graph answers "what code depends on what?" Arcbrain must answer "what operating work can we remove, why do we believe that, what changes, and what is the replacement architecture?"

Source: https://github.com/DeusData/codebase-memory-mcp

## Current Arcbrain Diagnosis

Current strengths:

- True WebGL/Three renderer is now in place.
- Arcbrain has layers for process, metadata, evidence, replacement, and code.
- Search returns nodes, edges, paths, confidence, assumptions, missing evidence, and suggested questions.
- `codebase-memory-mcp` is integrated as a code graph adapter.
- Existing backend already has document and metadata vectorization infrastructure outside Arcbrain search.

Current gaps:

- Default graph view is still too raw. It renders up to 1,400 nodes, which reads as a data cloud rather than an executive brain.
- Arcbrain search is still mostly keyword matching over graph nodes, plus incident edge/path collection. It does not yet use semantic vector retrieval, community summaries, code search, or LLM synthesis as the primary answer engine.
- The code graph is globally injected from the configured backend repo. For commercial use, repo ingestion must be tenant-scoped.
- The scene has a 3D renderer, but not a fully designed spatial grammar. Users see nodes in space, but they do not immediately understand what space means.
- The "consulting nodes" behavior exists, but the experience does not yet feel like a deliberative system showing its reasoning.

## Should We Hide Vectors Or Show Only Code?

### Hide Raw Vectors

Yes. Raw vectors should never be first-class UX. They are retrieval infrastructure, not executive meaning. We should expose evidence coverage, confidence, source freshness, contradiction, and semantic clusters. We should not show "vectors" as visual objects.

### Do Not Show Only Code

No. A code-only graph is impressive to engineers, but it would collapse Arcbrain into a developer tool. It may help a CTO understand implementation risk, but it will not answer the executive replacement question by itself.

### Make Code A Source Layer

Code should be a selectively revealed implementation substrate:

- Show code when a recommendation depends on a custom app, integration, API route, Flow, Apex class, or background job.
- Show code in "Build Plan" and "Implementation Risk" modes.
- Keep it hidden in the default executive overview unless it is directly part of the answer path.

## Recommended Product Direction

### Default Mode: Executive Brain

Default view should show 60-150 aggregated semantic beacons, not 1,400 raw nodes.

Beacons:

- Business domains
- High-value processes
- Manual handoff clusters
- Systems of record
- Automation clusters
- Evidence communities
- Replacement opportunities
- Key risks/blockers
- Agent design packages

Each beacon is clickable and expandable. Expansion reveals the supporting raw nodes only inside the selected cluster.

### Source Mode: Graph Inspector

A secondary mode for architects and delivery teams should expose the detailed graph:

- Salesforce metadata
- Fields
- Flows
- Apex/components
- Code files/functions/routes
- Documents/chunks/claims
- Low-level dependencies

This can keep the current renderer lineage, but it should be framed as source inspection, not the executive landing experience.

### Conversation Mode: Ask The Brain

Asking a question should visually change the entire scene:

1. Dim the full graph.
2. Light up the communities Arcbrain is consulting.
3. Animate a path through process, metadata, evidence, code, recommendation, and risk nodes.
4. Move the camera to the answer path.
5. Show a compact answer with citations that can focus the exact node.
6. Keep missing evidence visible as a first-class trust signal.

The goal is not theatrical excess. It should feel like an executive intelligence instrument revealing what it knows.

### Spatial Grammar

3D space should mean something:

- Center: operating domains and replacement opportunities.
- Left/back: evidence, source documents, inferred claims.
- Right/front: recommendations, agent packages, implementation path.
- Lower depth: systems, metadata, code, integrations.
- Upper depth: executive-level processes, teams, outcomes, controls.

This lets the user build spatial memory. "The code layer is below the process it supports" is more meaningful than a random galaxy.

## Visual Upgrade Concepts

### 1. Arcbrain Command Surface

Make the graph area more dominant. The left rail becomes a compact command bar or overlay. The right rail becomes answer evidence, not always-open technical details.

Key effect: the first glance is the brain, not three admin columns.

### 2. Semantic Beacons

Replace most small nodes in default view with larger, labeled beacons:

- Beacon size = economic value / dependency centrality.
- Beacon ring = confidence / evidence coverage.
- Beacon color = layer, with orange only for active focus/action.
- Beacon shadow or dashed ring = missing evidence.

Raw nodes appear only after selecting or asking.

### 3. Evidence Path Animation

When Arcbrain answers, animate sequential "consulted" nodes:

`Question -> process -> handoff -> Salesforce object/Flow -> evidence claim -> recommendation -> agent package`

Each step should have a visible label and citation chip. This is the real "talk to the system" moment.

### 4. Lens-Specific Worlds

The same data should rearrange by lens:

- Overview: semantic beacons and operating domains.
- Replacement Heat: opportunity clusters, savings, confidence, risk.
- Blast Radius: selected node in center, dependencies as upstream/downstream rings.
- Trust: evidence, assumptions, stale/missing sources, contradiction risk.
- Code Intelligence: repo/project/service map with links back to business processes.

### 5. Guided Executive Questions

Templates should not be generic buttons. They should become investigation modes:

- "What work can we remove?" opens replacement heat.
- "What breaks if we automate this?" opens blast radius.
- "Why should I trust this?" opens trust path.
- "What would we need to build?" opens code + agent package path.

## Intelligence Upgrade

Arcbrain search should become a graph-grounded answer pipeline:

1. Parse intent: replacement, risk, dependency, trust, implementation, cost.
2. Retrieve with multiple signals:
   - graph keyword matches
   - document vector search
   - metadata/community vector search
   - code graph search
   - recommendation and process links
3. Build candidate evidence paths.
4. Rank by confidence, freshness, value, and relevance.
5. Generate an answer with cited graph nodes and missing evidence.
6. Return a visual trace contract for the renderer.

This uses existing vector infrastructure instead of exposing vectors directly.

## Implementation Plan

### Phase 1: Executive LOD Rescue

- Add `ArcbrainViewMode`: `executive_brain` and `source_graph`.
- Default to `executive_brain`.
- Add `buildArcbrainExecutiveScene()` that aggregates raw nodes into semantic beacons.
- Hide raw code/document chunk/field/function nodes by default.
- Preserve highlighted/search/focused nodes even when normally hidden.
- Add layer toggles: Operating Model, Salesforce, Evidence, Replacement, Code.
- Keep source graph mode for current detailed view.

Expected impact: the page stops looking like a raw data dump.

### Phase 2: Conversation Theater

- Add `conversationTrace` to frontend state.
- Animate consulted nodes and supporting edges in sequence.
- Auto-focus the camera on the answer path after an ask.
- Make answer citations click-to-fly-to-node.
- Add "Arcbrain consulted..." timeline in the answer panel.

Expected impact: it starts to feel like talking to the customer's system.

### Phase 3: Semantic Arcbrain Search

- Extend backend search to call document/community vector search.
- Add code graph search only for implementation/code intents.
- Rank evidence paths.
- Generate graph-grounded answer text with citations, assumptions, and missing proof.

Expected impact: the visual becomes meaningful because the answer path is actually retrieved, not keyword-matched.

### Phase 4: Tenant-Scoped Code Intelligence

- Replace global `ARCBRAIN_CODEGRAPH_REPOS` behavior with tenant/client repo mapping.
- Add org-level code project configuration.
- Store provider/version/checksum/index freshness in snapshot summary.
- Only show code layer for repos explicitly attached to that client/org.

Expected impact: code intelligence becomes commercially sane and customer-relevant.

### Phase 5: Visual Polish

- Add GPU-friendly beacon materials and subtle depth fog.
- Add edge bundling or path-only edge rendering in executive mode.
- Use SDF or sprite labels for key beacons only.
- Add selected-node orbit ring and evidence confidence ring.
- Use orange only for current focus/action.
- Add reduced-motion static equivalents.

Expected impact: executive-grade wow without generic sci-fi noise.

## Product Bet

Arcbrain should become:

> a guided, evidence-backed operating brain that lets an executive ask what work can be removed and watch the system prove its answer.

That is stronger than a pretty code graph. The code graph matters, but it is the implementation x-ray. The executive product is the operating brain.

