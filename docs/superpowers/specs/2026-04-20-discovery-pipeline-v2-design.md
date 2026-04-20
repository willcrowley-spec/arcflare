# Discovery Pipeline v2 — Evidence-Grounded Architecture

**Date:** 2026-04-20
**Status:** Draft
**Supersedes:** [Process Discovery Engine Design](2026-04-17-process-discovery-engine-design.md) (pipeline stages only; data model additions are additive)

## Problem

The current 7-stage pipeline takes 24+ minutes for a small org, burns ~250K tokens per run, and produces process descriptions that cannot be traced back to the data that proves they exist. The core issues:

1. **Context stuffing** — Each stage dumps the entire org metadata summary + all document chunks into the prompt. Research shows accuracy drops 30%+ when irrelevant context is included ("lost in the middle" effect — Liu et al. 2023).
2. **No provenance** — We graph and vectorize every piece of Salesforce metadata and every uploaded document, but the pipeline treats that infrastructure as a keyword search fallback. Discovered processes cite nothing. A user can't click on "Lead Qualification" and see *which* Flow, *which* object, *which* document passage proved it exists.
3. **Redundant LLM passes** — Stages 2→3→4→5 each re-process overlapping information. The "Revision or Re-Solving?" paper (Kamoi et al. 2025) shows multi-pass revision rarely improves structured extraction — it just burns tokens.
4. **Rate-limit bottleneck** — Anthropic Tier 1 limits (30K input TPM) mean most wall-clock time is spent sleeping in backoff. Moving to Gemini helped throughput but doesn't fix the architectural waste.

## Research Foundation

Architecture decisions are grounded in these findings (full details in [discovery-performance-research.md](2026-04-20-discovery-performance-research.md)):

| Principle | Source | Impact |
|-----------|--------|--------|
| Context stuffing kills accuracy | "Lost in the Middle" (Liu et al. 2023) | Only feed evidence directly relevant to the extraction target |
| Element-wise extraction > monolithic | EVE Framework (Deng et al. 2025) — 24-31% F1 gain | Extract per-domain, not all-at-once |
| Evidence citation reduces hallucination | Evidence Bundle-Enforced RAG — 23.7% → 3.2% hallucination rate | Force the LLM to cite specific source IDs |
| Independent verification catches errors | Chain of Verification (Dhuliawala et al. 2023) | Separate verification from generation |
| Multi-pass revision wastes tokens | "Revision or Re-Solving?" (Kamoi et al. 2025) | Single focused pass > iterative refinement |
| Community summaries enable routing | GraphRAG (Microsoft, 2024) | Use community structure to scope retrieval |

## Design Principles

1. **Evidence-first** — No claim without a citation. Every process, step, actor, and touchpoint traces to a specific `MetadataObject`, `MetadataAutomation`, `MetadataComponent`, `DocumentChunk`, or `Community`.
2. **Retrieve, don't stuff** — Each LLM call gets a scoped evidence bundle assembled via vector search + graph traversal. Target: <4K tokens of evidence per domain, not 15K+ of everything.
3. **One focused pass** — A single extraction call per domain replaces the current 4-stage decomposition (stages 2-5). Fewer calls = less latency = less cost.
4. **Verify independently** — A separate, lightweight verification pass checks citations against actual data. Generation and verification are decoupled per EVE/CoVe.
5. **Stored provenance** — Evidence links are persisted on the `BusinessProcess` model and surfaced in the UI. The user can audit every claim.

---

## Data Model Changes

### `BusinessProcess` — New Column

| Column | Type | Purpose |
|--------|------|---------|
| `evidence_sources` | `JSONB` | Array of evidence objects linking this process/step to source data |

Default: `'[]'::jsonb`

#### `evidence_sources` Schema

```json
[
  {
    "type": "metadata_object",
    "id": "uuid",
    "api_name": "Lead",
    "label": "Lead",
    "relevance": "Primary object — record lifecycle drives this process",
    "confidence": 0.95
  },
  {
    "type": "automation",
    "id": "uuid",
    "api_name": "Lead_Assignment_Flow",
    "label": "Lead Assignment",
    "relevance": "Automates lead routing to queues based on territory",
    "confidence": 0.9
  },
  {
    "type": "document_chunk",
    "chunk_id": "uuid",
    "document_id": "uuid",
    "document_name": "Sales Playbook Q1.pdf",
    "excerpt": "Leads are qualified using BANT criteria before...",
    "relevance": "Describes qualification criteria and handoff to AE",
    "confidence": 0.85
  },
  {
    "type": "component",
    "id": "uuid",
    "api_name": "LeadScoringBatch",
    "category": "apex_class",
    "relevance": "Batch job that computes lead scores nightly",
    "confidence": 0.8
  },
  {
    "type": "community",
    "id": "uuid",
    "label": "Lead Management Cluster",
    "relevance": "Metadata community containing Lead, Campaign, CampaignMember",
    "confidence": 0.7
  }
]
```

Each evidence entry has:
- `type` — one of `metadata_object`, `automation`, `component`, `document_chunk`, `community`
- `id` / `chunk_id` — UUID referencing the actual DB row
- Human-readable identifiers (`api_name`, `label`, `document_name`, `excerpt`)
- `relevance` — one-sentence explanation of why this evidence supports this process
- `confidence` — 0.0-1.0 LLM's confidence that this evidence is actually relevant

### `ProcessHandoff` — New Column

| Column | Type | Purpose |
|--------|------|---------|
| `evidence_sources` | `JSONB` | Evidence supporting this specific handoff relationship |

Same schema as above. Cross-domain handoffs cite the automations/integrations that bridge domains.

### Migration

Single Alembic migration (021): `ALTER TABLE business_processes ADD COLUMN IF NOT EXISTS evidence_sources JSONB NOT NULL DEFAULT '[]'::jsonb` + same for `process_handoffs`. Idempotent, no index needed (JSONB GIN only worth it if we query inside the array, which we won't — we read the whole array for display).

---

## New Pipeline Architecture

### Overview

```
Phase 1: Domain Discovery          1 LLM call     (Opus)
Phase 2: Evidence Assembly          0 LLM calls    (vector search + graph traversal)
Phase 3: Per-Domain Extraction      D LLM calls    (Gemini Flash)
Phase 4: Evidence Verification      D LLM calls    (Gemini Flash)
Phase 5: Cross-Domain Synthesis     1 LLM call     (Gemini Flash)
Phase 6: Quality Scoring            0 LLM calls    (heuristic)
Phase 7: Graph Generation           0 LLM calls    (existing)
```

Where D = number of discovered domains (typically 3-6).

**Total LLM calls**: 2D + 2 (vs current ~5D + 2)
**Target wall-clock**: <5 minutes for a small org (vs 24+ today)

---

### Phase 1: Domain Discovery (kept, improved)

**Purpose**: Identify the 3-6 business domains present in this org.

**Changes from current Stage 1**:
- Still uses Opus (high-reasoning for the most consequential decision)
- Context is tighter: org profile + community summaries only (no raw metadata dump)
- Output adds a `key_objects` array per domain — the LLM's hypothesis about which Salesforce objects are central to each domain. This seeds Phase 2 retrieval.

**Input context** (~2-3K tokens):
- Org profile (name, industry, business model, description)
- Top 8-10 metadata community summaries (from `get_relevant_metadata_summaries`)
- Top 5 document community summaries (from `Community` where `source='document'`)
- Object inventory: just api_name + record_count for objects with data (one line each)

**Output schema** (extends current):
```json
{
  "domains": [
    {
      "name": "Lead Management",
      "description": "...",
      "key_objects": ["Lead", "Campaign", "CampaignMember"],
      "key_terms": ["lead scoring", "qualification", "MQL"],
      "confidence": 0.9
    }
  ]
}
```

The `key_objects` and `key_terms` arrays are retrieval seeds — they drive Phase 2.

---

### Phase 2: Evidence Assembly (new, no LLM)

**Purpose**: For each domain from Phase 1, assemble a focused evidence bundle using vector search and graph traversal. Zero LLM calls.

**Algorithm per domain**:

1. **Seed expansion via graph**: Take `key_objects` from Phase 1. Query `MetadataDependency` to find all objects/automations/components within 2 hops. This gives us the "neighborhood" of each domain's core objects.

2. **Metadata retrieval**: Load full details for the expanded object set from `MetadataObject`, `MetadataAutomation`, `MetadataComponent`. Include fields, relationships, record types for objects; trigger conditions, actions for automations.

3. **Document chunk retrieval**: Run `batch_semantic_search` with 2-3 queries derived from domain name + key_terms. Take top 5-8 chunks per domain. These are the *only* document passages the extraction call will see.

4. **Community context**: Include the metadata community summary whose `member_concept_ids` best overlap with the expanded object set.

5. **Deduplication**: If an object/automation appears in multiple domain bundles, it belongs to whichever domain's `key_objects` it's closest to (by graph distance). Prevents duplicate process discovery.

**Output per domain**: An `EvidenceBundle` dataclass:
```python
@dataclass
class EvidenceBundle:
    domain: dict                           # from Phase 1
    metadata_objects: list[dict]           # id, api_name, label, fields, relationships, record_types
    automations: list[dict]               # id, api_name, type, trigger, actions
    components: list[dict]                # id, api_name, category, description
    document_chunks: list[dict]           # chunk_id, document_id, document_name, content, section_title
    community_summary: str | None         # community narrative
    dependency_edges: list[dict]          # source→target typed edges
```

**Token budget**: Target <4K tokens per bundle. Truncate individual items if needed (fields list → top 20 custom fields only, etc.).

---

### Phase 3: Per-Domain Extraction (replaces stages 2-5)

**Purpose**: From a single evidence bundle, extract the full process hierarchy for one domain — processes, subprocesses, steps, actors, touchpoints, triggers, flows, handoffs — in one call. Every claim must cite its evidence.

**Model**: Gemini 2.5 Flash (fast, cheap, good structured output). Falls back to Sonnet if quality issues detected.

**Prompt structure** (3 sections):
1. **System** (~800 tokens): Extraction protocol, output schema definition, citation requirements
2. **Evidence bundle** (~3-4K tokens): The assembled bundle from Phase 2, with each item tagged with a stable reference ID (e.g., `[OBJ-1]`, `[AUTO-3]`, `[DOC-5]`)
3. **Task** (~200 tokens): "Extract all business processes for the {domain_name} domain. Every process, step, actor, and touchpoint MUST cite at least one evidence reference."

**Output schema**:
```json
{
  "processes": [
    {
      "name": "Lead Qualification",
      "level": "process",
      "description": "...",
      "narrative": "...",
      "evidence_refs": ["OBJ-1", "AUTO-3", "DOC-5"],
      "confidence": 0.9,
      "actors": [
        {"name": "Sales Rep", "type": "user", "evidence_refs": ["DOC-5"]}
      ],
      "trigger_conditions": [
        {"description": "New lead created via web form", "evidence_refs": ["AUTO-1"]}
      ],
      "system_touchpoints": [
        {"name": "Lead", "type": "object", "evidence_refs": ["OBJ-1"]}
      ],
      "decision_logic": [
        {"description": "BANT score >= 70 triggers MQL status", "evidence_refs": ["DOC-5", "AUTO-3"]}
      ],
      "success_criteria": [
        {"description": "Lead converted to Opportunity", "evidence_refs": ["OBJ-1"]}
      ],
      "failure_modes": [
        {"description": "Lead stale >30 days with no activity", "evidence_refs": ["AUTO-7"]}
      ],
      "value_classification": "core",
      "complexity_score": "medium",
      "automation_potential": "high",
      "children": [
        {
          "name": "Initial Lead Scoring",
          "level": "step",
          "description": "...",
          "evidence_refs": ["AUTO-3", "OBJ-1"],
          "sequencing": {"position": 1, "parallel_group": null},
          "...": "..."
        }
      ]
    }
  ],
  "intra_domain_handoffs": [
    {
      "source": "Lead Qualification",
      "target": "Opportunity Creation",
      "type": "automated",
      "description": "Lead conversion trigger",
      "evidence_refs": ["AUTO-5"]
    }
  ]
}
```

The `evidence_refs` arrays use the tagged IDs from the prompt. Post-processing resolves these back to actual DB UUIDs for storage in `evidence_sources`.

**Concurrency**: All D domain extraction calls run in parallel (one per domain). With Gemini Flash's 4M TPM limit, no rate limiting concern.

---

### Phase 4: Evidence Verification (new)

**Purpose**: Independent pass that checks whether citations are accurate. Catches hallucinated evidence links and inflated confidence scores.

**Model**: Gemini 2.5 Flash.

**Algorithm per domain**:
1. Take the extraction output from Phase 3
2. For each process/step, take each `evidence_ref` and look up what the ref actually contains (from the original evidence bundle)
3. Ask the LLM: "Does [evidence item] actually support [claim]? Rate: CONFIRMED / WEAK / UNSUPPORTED"
4. Processes where >50% of evidence is UNSUPPORTED get `needs_review = true`
5. Individual claims with UNSUPPORTED evidence get their `evidence_sources` entry removed and `confidence` reduced

**Prompt structure** (~2K tokens per domain):
1. **System** (~400 tokens): Verification protocol — be skeptical, check factual grounding
2. **Claims + Evidence pairs** (~1.5K): Structured list of "Claim: X, Evidence: Y" pairs
3. **Task**: "For each claim-evidence pair, determine if the evidence genuinely supports the claim."

**Output schema**:
```json
{
  "verifications": [
    {
      "process_name": "Lead Qualification",
      "claim": "BANT score >= 70 triggers MQL",
      "evidence_ref": "DOC-5",
      "verdict": "CONFIRMED",
      "reasoning": "Document explicitly states BANT threshold of 70 for MQL status"
    },
    {
      "process_name": "Lead Qualification",
      "claim": "Nightly batch job computes lead scores",
      "evidence_ref": "AUTO-3",
      "verdict": "WEAK",
      "reasoning": "Flow triggers on record update, not on a schedule. Claim about 'nightly' is not supported."
    }
  ]
}
```

**Concurrency**: Runs in parallel across domains, same as Phase 3.

**Fail-safe**: If verification can't run (LLM error), the extraction output is kept as-is with a flag on the run indicating verification was skipped. We don't silently drop data.

---

### Phase 5: Cross-Domain Synthesis (kept, scoped)

**Purpose**: Identify handoffs, gaps, and relationships between domains. Produces cross-domain `ProcessHandoff` rows.

**Changes from current Stage 6**:
- Input is the verified process tree only (not raw metadata)
- Each domain summary includes its top evidence sources, so the synthesis can cite what bridges domains
- Output `ProcessHandoff` rows include `evidence_sources`

**Model**: Gemini 2.5 Flash.

**Input context** (~3-5K tokens):
- Org profile (compact)
- Per-domain: domain name, process names, key objects, key automations (from verified evidence)
- Dependency edges that cross domain boundaries (from `MetadataDependency` where source is in domain A, target in domain B)

**Output schema** (same as current with `evidence_refs` added):
```json
{
  "cross_domain_handoffs": [
    {
      "source_domain": "Lead Management",
      "source_process": "Lead Qualification",
      "target_domain": "Sales Pipeline",
      "target_process": "Opportunity Creation",
      "type": "automated",
      "description": "Lead conversion creates Opportunity",
      "evidence_refs": ["AUTO-5", "OBJ-1"],
      "confidence": 0.9,
      "is_gap": false
    }
  ],
  "domain_narratives": [
    {
      "domain": "Lead Management",
      "narrative": "..."
    }
  ]
}
```

---

### Phase 6: Quality Scoring (kept, enhanced)

No LLM. Same heuristic scoring as current Stage 7, with additions:

- **Evidence coverage score**: What % of processes have ≥1 confirmed evidence source? Target: >80%.
- **Verification pass rate**: What % of claims passed verification? Stored on `DiscoveryRun.quality_scores`.
- **Orphan detection**: Processes with zero evidence after verification are flagged `needs_review`.

---

### Phase 7: Graph Generation (unchanged)

Existing `generate_graphs_for_run` — produces `ProcessNode` / `ProcessEdge` rows for visualization.

---

## Evidence Resolution

The LLM works with tagged references (`[OBJ-1]`, `[AUTO-3]`, `[DOC-5]`). Post-processing resolves these to the `evidence_sources` JSONB stored on each `BusinessProcess`:

```python
def resolve_evidence_refs(
    evidence_bundle: EvidenceBundle,
    evidence_refs: list[str],
    verifications: dict[str, str] | None,
) -> list[dict]:
    """Convert tagged refs to stored evidence_sources entries.
    
    Drops refs that failed verification (verdict=UNSUPPORTED).
    Includes human-readable fields for UI display.
    """
```

The reference tag format:
- `OBJ-{n}` → `metadata_objects[n]` in the bundle
- `AUTO-{n}` → `automations[n]`
- `COMP-{n}` → `components[n]`
- `DOC-{n}` → `document_chunks[n]`
- `COMM` → community summary

---

## Token Budget Analysis

### Current Pipeline (measured on a small org)

| Stage | Calls | Input tokens/call | Output tokens/call | Total |
|-------|-------|-------------------|-------------------|-------|
| 1 (Domain) | 1 | ~12K | ~2K | 14K |
| 2 (Structure) | D×1 | ~15K | ~4K | D×19K |
| 3+4 (Enrich+Flow) | D×1 | ~14K | ~8K | D×22K |
| 5 (Validation) | D×1 | ~12K | ~3K | D×15K |
| 6 (Synthesis) | 1 | ~8K | ~4K | 12K |
| **Total (D=4)** | | | | **~250K** |

### New Pipeline (projected)

| Phase | Calls | Input tokens/call | Output tokens/call | Total |
|-------|-------|-------------------|-------------------|-------|
| 1 (Domain) | 1 | ~3K | ~1K | 4K |
| 2 (Evidence) | 0 | — | — | 0 |
| 3 (Extraction) | D×1 | ~5K | ~4K | D×9K |
| 4 (Verification) | D×1 | ~2K | ~1K | D×3K |
| 5 (Synthesis) | 1 | ~4K | ~2K | 6K |
| **Total (D=4)** | | | | **~58K** |

**Projected reduction**: ~77% fewer tokens. Majority of remaining tokens are in Phase 3 (the actual extraction work).

---

## Model Assignment

| Phase | Model | Rationale |
|-------|-------|-----------|
| 1 — Domain Discovery | Claude Opus | Highest-stakes decision — wrong domains cascade errors. Opus reasoning is worth the cost for 1 call. |
| 3 — Per-Domain Extraction | Gemini 2.5 Flash | Structured extraction from focused evidence. Flash handles this well; 4M TPM means no rate limits. |
| 4 — Evidence Verification | Gemini 2.5 Flash | Binary classification (CONFIRMED/WEAK/UNSUPPORTED) — lightweight task. |
| 5 — Cross-Domain Synthesis | Gemini 2.5 Flash | Moderate reasoning from compact input. |

**Prompt caching**: Phase 3 benefits — system instructions are identical across all D calls. Anthropic cache on Phase 1 system prompt is irrelevant (single call). LiteLLM handles cache_control passthrough for whichever provider supports it.

---

## Concurrency Model

```
Phase 1 ──────────────────────────> (1 call, sequential)
Phase 2 ──┬── Domain A assembly
           ├── Domain B assembly     (all parallel, no LLM)
           └── Domain C assembly
Phase 3 ──┬── Domain A extraction
           ├── Domain B extraction   (all parallel, Gemini Flash)
           └── Domain C extraction
Phase 4 ──┬── Domain A verification
           ├── Domain B verification (all parallel, Gemini Flash)
           └── Domain C verification
Phase 5 ──────────────────────────> (1 call, sequential)
Phase 6 ──────────────────────────> (heuristic, instant)
Phase 7 ──────────────────────────> (graph gen, instant)
```

Phases 3 and 4 *could* be pipelined (start verification for domain A as soon as extraction finishes, while B/C are still extracting), but the added complexity isn't worth it — all D calls finish within seconds on Flash.

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| Phase 1 fails | Abort run. No domains = nothing to extract. |
| Phase 2 returns empty evidence for a domain | Skip that domain, log warning. If all domains empty, abort. |
| Phase 3 extraction fails for one domain | Retry 2x. If still failing, skip domain, mark run as partial. |
| Phase 3 returns uncitable claims | Phase 4 catches these — they get UNSUPPORTED verdicts. |
| Phase 4 verification fails | Keep extraction output as-is, flag `verification_skipped` on run. |
| Phase 5 synthesis fails | Retry 2x. If failing, persist per-domain results without cross-domain handoffs. |

---

## Migration & Rollout

1. **Migration 021**: Add `evidence_sources` column to `business_processes` and `process_handoffs`. Idempotent.
2. **Feature flag**: `discovery_v2` in org settings. Default off. Old pipeline remains available.
3. **Parallel runs**: During testing, run both v1 and v2 on the same org and compare quality scores.
4. **UI**: Add evidence panel to process detail view — clickable links to source metadata/documents.
5. **Deprecation**: Once v2 quality is confirmed ≥ v1 across 5+ orgs, remove v1 code paths.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/models/process.py` | Add `evidence_sources` column |
| `backend/app/models/discovery.py` | Add `evidence_sources` to `ProcessHandoff` |
| `backend/alembic/versions/021_evidence_sources.py` | Migration |
| `backend/app/services/processes/discovery.py` | Full rewrite of pipeline orchestration |
| `backend/app/services/processes/context.py` | New `assemble_evidence_bundle` function; keep existing vector search utils |
| `backend/app/services/processes/prompts.py` | New prompt builders for phases 1, 3, 4, 5 |
| `backend/app/services/processes/evidence.py` | **New** — evidence resolution + verification logic |
| `backend/app/services/ai/response_schemas.py` | New schemas for phases 1, 3, 4, 5 |
| `backend/app/services/ai/operations.py` | New operation entries for v2 phases |
| `backend/app/workers/process_discovery.py` | Updated orchestration calling v2 pipeline |
| `backend/app/schemas/process.py` | Add `evidence_sources` to API response schemas |
| `frontend/` | Evidence panel component (future — not in initial implementation) |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Wall-clock time (small org) | 24 min | <5 min |
| Total tokens per run | ~250K | <60K |
| LLM calls per run (D=4) | ~18 | ~10 |
| Evidence coverage (% processes with ≥1 source) | 0% | >80% |
| Verification pass rate | N/A | >85% |
| Needs-review flag accuracy | Unknown | Tracked via Langfuse |

---

## Open Questions

1. **Opus vs Sonnet for Phase 1**: Opus is expensive for a single call but domains are the foundation. Run A/B test after v2 ships.
2. **Evidence bundle token budget**: 4K target is a guess. May need tuning per org size. Add Langfuse tracking.
3. **Verification granularity**: Per-claim verification is thorough but adds latency. Could batch-verify per-process instead of per-claim if wall-clock is still too high.
4. **Document chunk quality**: If uploaded documents are low-quality (scanned PDFs with OCR errors), evidence citations will be weak regardless. Consider a chunk quality score gate.
