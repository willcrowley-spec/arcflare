# Document Ingestion & Knowledge Layer Design

**Date**: 2026-04-19
**Status**: Approved
**Scope**: Enhanced document ingestion pipeline, LazyGraphRAG-style knowledge layer, Smart Document Library UI, incremental amendment notifications

---

## Context & Problem Statement

Arcflare's current document pipeline handles the basics — upload, parse, chunk, embed, store in pgvector — but lacks several capabilities needed for production-quality process discovery:

1. **No deduplication**: Re-uploading the same file re-processes it entirely. No content hash exists on the Document model.
2. **No structured knowledge extraction**: Documents are chunked and embedded but not analyzed for entities, concepts, or relationships. NER code exists in `services/extraction/ner.py` but has zero call sites — it is not wired into the vectorization pipeline. Process discovery relies on flat vector search. Microsoft's GraphRAG evaluation ([arXiv:2404.16130](https://arxiv.org/abs/2404.16130)) shows graph-enhanced retrieval produces substantially higher LLM-judge win rates for comprehensiveness (72-83%) and diversity (62-82%) vs. vector-only baselines on global sensemaking queries.
3. **No provenance tracking**: No junction table or FK links business processes to the documents that informed them. `BusinessProcess` has no `document_id`; discovery links runs but not source documents.
4. **No document management UI**: API routes exist in `documents.py` but no `/documents` route in `App.tsx`. Additionally, the frontend API client posts to `POST /documents` while the backend handler is at `POST /documents/upload` — this path mismatch must be fixed.
5. **No incremental updates**: Adding a document requires re-running the full discovery pipeline to incorporate its knowledge.
6. **Incomplete delete**: Removing a document deletes DB rows via cascade but leaves the file on disk at `storage_path`.

Josh's `arcflare-local-demo` repo implemented a full pipeline (parse -> NER -> chunk -> embed -> Neo4j knowledge graph -> connection agent -> synthesis agent) but targeted a single-tenant local CLI. This design adapts the relevant patterns for our multi-tenant web platform, informed by 2026 industry research.

---

## Research Summary

### Sources Consulted

- **Microsoft GraphRAG** ([arXiv:2404.16130](https://arxiv.org/abs/2404.16130)) — community detection, global sensemaking evaluation
- **Microsoft LazyGraphRAG** ([research blog](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)) — deferred LLM indexing, NLP noun-phrase graph, benchmark comparisons
- **Microsoft GraphRAG OSS** ([github.com/microsoft/graphrag](https://github.com/microsoft/graphrag)) — NLP extraction implementation, PMI edge weighting, Leiden defaults
- **Google Vertex AI RAG Engine** — data connector architecture, layout-aware chunking, dedup patterns
- **LangChain document loader architecture** — BaseLoader abstraction, Confluence/SharePoint connectors
- **Particula Tech** — incremental RAG update patterns, delta indexing, metadata versioning
- **Everstone AI** — GDPR vector deletion compliance, delta-sync indexes
- **pgvector maintainer guidance** ([issue #335](https://github.com/pgvector/pgvector/issues/335), [issue #450](https://github.com/pgvector/pgvector/issues/450)) — HNSW delete/vacuum behavior
- **Apache AGE / Piggie benchmarks** ([github.com/gregfelice/piggie](https://github.com/gregfelice/piggie)) — PostgreSQL graph extension performance
- **Leiden algorithm** — Traag, Waltman, van Eck (2019) ([DOI:10.1038/s41598-019-41695-z](https://www.nature.com/articles/s41598-019-41695-z))
- **OHRBench** ([arXiv:2412.02592](https://arxiv.org/abs/2412.02592)) — OCR/parsing noise impact on RAG quality
- **spaCy noun chunks** ([docs](https://spacy.io/usage/linguistic-features#noun-chunks), [issue #4356](https://github.com/explosion/spaCy/issues/4356)) — extraction quality across models

### Key Findings

| Finding | Source | Impact |
|---------|--------|--------|
| Graph-enhanced retrieval produces substantially higher LLM-judge win rates for comprehensiveness (72-83%) and diversity (62-82%) vs. vector-only baselines on global sensemaking queries | Microsoft GraphRAG paper, [arXiv:2404.16130](https://arxiv.org/abs/2404.16130) | Directly benefits process discovery |
| LazyGraphRAG achieves comparable quality at ~0.1% of GraphRAG indexing cost by deferring LLM calls to query time; at Z500 config, it won all 96 head-to-head comparisons across methods in Microsoft's AP News benchmark | Microsoft Research blog; corroborated by [Particula Tech](https://particula.tech/blog/lazygraphrag-700x-cheaper-graphrag-knowledge-graphs) | Eliminates cost barrier to graph-enhanced retrieval |
| NLP noun phrase extraction + community detection replaces expensive LLM entity extraction; Microsoft's OSS GraphRAG implements this as the `extract_graph_nlp` workflow with spaCy + PMI edge weighting | [GraphRAG OSS](https://github.com/microsoft/graphrag) `build_noun_graph` module | Indexing cost stays identical to current vector pipeline |
| Apache AGE adds Cypher graph queries to PostgreSQL; Piggie benchmarks show AGE won all 12 workloads vs Neo4j, with 25x speedup specifically on concurrent queries at 1M nodes (other workloads: 2-13x) | [Piggie README](https://github.com/gregfelice/piggie), [ooxo.io benchmarks](https://ooxo.io/graph-database-benchmarks/) | No new infrastructure needed |
| Content hashing eliminates redundant processing of unchanged files; savings are proportional to the ratio of unchanged-to-changed documents (typically significant in production) | Engineering consensus; Particula Tech | Prevents wasted processing on unchanged content |
| pgvector HNSW supports deletes natively; graph is repaired during vacuum, no reindex needed for normal churn; bulk deletes may benefit from drop-index/rebuild pattern | pgvector maintainer, [issue #335](https://github.com/pgvector/pgvector/issues/335), [issue #450](https://github.com/pgvector/pgvector/issues/450) | Our FK cascade handles row deletion; add vacuum planning for bulk ops |
| Enterprise RAG systems universally adopt hybrid storage (upload + connectors) | Google, LangChain, Katonic AI | Validates phased hybrid approach |

### Important Caveat: LazyGraphRAG Query Engine

Microsoft's open-source GraphRAG library (as of v2.7+) includes the **NLP graph indexing pipeline** (noun phrase extraction, co-occurrence graph, PMI weighting, Leiden community detection) but does **not** ship a fully packaged LazyGraphRAG query engine with `relevance_budget` parameter ([maintainer confirmation, issue #1692](https://github.com/microsoft/graphrag/issues/1692)). The query-time "iterative deepening search with budgeted relevance testing" described in Microsoft's blog is a **design pattern** we implement ourselves, not a drop-in library call. DataStax's [Lazy GraphRAG example](https://datastax.github.io/graph-rag/examples/lazy-graph-rag/) provides a concrete reference implementation using `GraphRetriever` with `max_depth`, `k`, and community-based claim extraction.

---

## Architecture

### System Overview

```
Document Upload
       │
       ▼
┌──────────────┐
│  Dedup Check  │  SHA-256 content hash against existing docs
│  (sync)       │
└──────┬───────┘
       │ new document
       ▼
┌──────────────┐
│  Disk Storage │  uploads/{org_id}/{doc_id}_{filename}
│  + DB Record  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│           Celery Vectorization Task            │
│                                                │
│  1. Parse (unstructured/openpyxl/text)         │
│  2. Chunk (adaptive: 256/512/1024 tokens)      │
│  3. Embed (Gemini 3072d → pgvector)            │
│  4. Extract concepts (NLP noun phrases)        │
│  5. Build/update concept co-occurrence graph   │
│  6. Re-run community detection (Leiden)        │
│  7. Link chunks → communities                  │
│  8. Identify affected processes (notify)        │
└──────────────────────────────────────────────┘
```

### Data Model Changes

#### New Tables

**`concepts`** — extracted noun phrases from document chunks

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| org_id | UUID | FK → organizations |
| name | VARCHAR(512) | normalized concept text |
| concept_type | VARCHAR(50) | noun_phrase, entity, system, role, etc. |
| frequency | INTEGER | total occurrences across all docs |
| created_at | TIMESTAMPTZ | |

Unique constraint on `(org_id, name)`.

**`concept_cooccurrences`** — edges in the concept graph

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| org_id | UUID | FK → organizations |
| concept_a_id | UUID | FK → concepts |
| concept_b_id | UUID | FK → concepts |
| raw_weight | INTEGER | raw co-occurrence count |
| pmi_weight | FLOAT | PMI-normalized weight (recomputed periodically) |
| document_ids | JSONB | array of doc IDs where co-occurrence was observed |

Unique constraint on `(org_id, concept_a_id, concept_b_id)` with `concept_a_id < concept_b_id` to avoid duplicate edges.

**`communities`** — topic clusters from Leiden algorithm

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| org_id | UUID | FK → organizations |
| parent_id | UUID | FK → communities (nullable, for hierarchy) |
| level | INTEGER | 0 = leaf, higher = more abstract |
| label | VARCHAR(512) | auto-generated from top concepts |
| member_concept_ids | JSONB | array of concept UUIDs in this community |
| metadata_json | JSONB | stats: doc_count, chunk_count, top_concepts |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**`chunk_communities`** — links chunks to their communities

| Column | Type | Notes |
|--------|------|-------|
| chunk_id | UUID | FK → document_chunks |
| community_id | UUID | FK → communities |

Composite PK on `(chunk_id, community_id)`.

**`process_document_sources`** — provenance tracking

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| process_id | UUID | FK → business_processes |
| document_id | UUID | FK → documents |
| chunk_ids | JSONB | specific chunks that informed this process |
| chunk_content_hashes | JSONB | SHA-256 of chunk content at retrieval time (for audit trail even if chunks are later re-indexed) |
| relevance_score | FLOAT | how relevant the doc was to this process |
| created_at | TIMESTAMPTZ | |

**Provenance capture**: Ground truth for "which chunks informed this process" is captured at the **retrieval layer**, not extracted from LLM output. When the process discovery pipeline retrieves chunks for context, persist the `(chunk_id, content_hash)` pairs in this table before sending to the LLM. Do not rely on LLM-generated citations as the sole provenance mechanism — models hallucinate citations at high rates ([GhostCite, arXiv:2602.06718](https://arxiv.org/abs/2602.06718)). LLM citations can be a **secondary signal** for UX but the system-of-record provenance is the retriever trace.

#### Modified Tables

**`documents`** — add columns:

| Column | Type | Notes |
|--------|------|-------|
| content_hash | VARCHAR(64) | SHA-256 of raw file bytes for dedup |
| concept_count | INTEGER | number of concepts extracted, default 0 |
| community_ids | JSONB | communities this document contributes to |
| embedding_model | VARCHAR(128) | model name used to embed this doc's chunks (for version tracking) |

**`document_chunks`** — add columns:

| Column | Type | Notes |
|--------|------|-------|
| concept_ids | JSONB | concepts extracted from this chunk |
| content_hash | VARCHAR(64) | SHA-256 of chunk text content (for provenance audit + chunk-level dedup) |

**Embedding model versioning**: Store `embedding_model` on each document to detect when the embedding model changes. Never mix embeddings from different models in the same queryable index without explicit routing — this causes silent retrieval degradation with no errors or exceptions. When upgrading models, re-embed all documents or maintain parallel indexes.

---

## Component Designs

### 1. Content Hashing & Dedup

At upload time, before writing to disk:

1. Stream the file through SHA-256 while writing to a temp buffer (always use incremental `hashlib.sha256().update(chunk)` — never load full file into memory)
2. Query `documents` for matching `content_hash` within the same `org_id`
3. If match found and status is `indexed`: return the existing document (skip re-processing)
4. If match found but status is `error`: allow re-upload (overwrite)
5. If no match: proceed with normal upload flow

The hash is computed on raw file bytes, not parsed content, so format differences (e.g., re-exported PDF) are treated as new documents.

**Known limitation**: SHA-256 on raw bytes will treat semantically identical files as different if their byte representations differ (re-exported PDFs, DOCX with different metadata/timestamps, etc.). This is an acceptable tradeoff for Phase 1 — byte-level dedup catches exact re-uploads which is the common case. Future enhancement: add a secondary `canonical_text_hash` (SHA-256 of normalized parsed text) for near-duplicate detection, with a pinned normalization spec (Unicode NFC, collapsed whitespace, stripped metadata).

### 2. NLP Concept Extraction

Runs as step 4 in the Celery vectorization task, after chunking and embedding (embedding does not depend on concepts and can run in parallel or before).

**Extraction method**: spaCy noun phrase extraction following Microsoft GraphRAG's `SyntacticNounPhraseExtractor` pattern. Key design decisions informed by GraphRAG's OSS implementation:

**Model choice**: `en_core_web_sm` for Phase 1 (fast, no GPU). Note: noun chunk quality varies across `sm`/`md`/`lg` because parser accuracy differs ([spaCy issue #4356](https://github.com/explosion/spaCy/issues/4356)). If extraction quality is insufficient on business/technical documents, upgrade to `en_core_web_md` (adds word vectors, better parsing). Benchmark with `spacy benchmark speed` on representative chunks before committing.

**Extraction pipeline** (per chunk):
1. Load spaCy with `lemmatizer` disabled (GraphRAG pattern — we normalize separately)
2. Merge named entities with noun chunks using `spacy.util.filter_spans` to avoid overlapping spans
3. Extract merged noun phrases
4. Normalize: **UPPERCASE** surface form (GraphRAG's choice for canonical key — simpler than lemmatization, handles "Sales Manager" == "sales manager"); store original surface form as display label
5. Filter: remove phrases < 2 characters or > 100 characters, remove pure stopword phrases, apply POS-based filters (keep NOUN/PROPN-headed phrases)
6. Upsert into `concepts` table (increment frequency if exists)
7. For each pair of concepts co-occurring in the same chunk: compute co-occurrence, upsert into `concept_cooccurrences`
8. Store concept IDs in `document_chunks.concept_ids`

**Edge weighting**: Use **PMI (Pointwise Mutual Information)** on co-occurrence edges, following GraphRAG's `calculate_pmi_edge_weights` implementation. Raw co-occurrence counts bias toward globally frequent terms; PMI emphasizes associations stronger than statistical independence. Apply **minimum co-occurrence threshold** (>= 2) before PMI to avoid overfitting low-frequency pairs. Optionally add **per-node top-K edge pruning** to control graph density.

**Co-occurrence window**: Within-chunk (all concept pairs in the same chunk form edges). This provides a natural, structure-aware window that respects document layout. Do not use document-wide windows — they produce dense, uninformative graphs with spurious hub nodes.

**Token budget**: spaCy `en_core_web_sm` runs locally, no API calls. Throughput depends on chunk length and CPU — benchmark locally; official spaCy benchmarks only publish WPS for `en_core_web_lg`. Expect order-of-magnitude tens of milliseconds per typical chunk on modern hardware.

### 3. Community Detection

Runs as step 6, after concept extraction completes for all chunks in the document.

**Algorithm**: Leiden community detection via `leidenalg` library (Traag, Waltman, van Eck, 2019 — [DOI:10.1038/s41598-019-41695-z](https://www.nature.com/articles/s41598-019-41695-z)). Operates on the concept co-occurrence graph for the org.

**Configuration** (aligned with GraphRAG defaults where applicable):
- **Partition type**: `RBConfigurationVertexPartition` (supports tunable resolution parameter, unlike `ModularityVertexPartition` which does not)
- **Resolution**: Start at `1.0` (GraphRAG default). Higher values → more smaller communities; lower → fewer larger ones. Use `leidenalg`'s `resolution_profile()` on representative org graphs to find stable resolution ranges.
- **Iterations**: `n_iterations=-1` (run until no improvement, not the default of 2 — gives better convergence)
- **Seed**: Fixed seed (`0xDEADBEEF`, GraphRAG convention) for reproducibility
- **Max community size**: `10` concepts per leaf community (GraphRAG default) — keeps communities interpretable

**Pipeline**:
1. Load concept co-occurrence graph for the org from `concept_cooccurrences` into an `igraph.Graph`
2. Apply PMI-weighted edges as graph weights
3. Run Leiden with above configuration
4. For hierarchical communities: run at multiple resolution levels via `resolution_profile()`, or use `aggregate_partition()` for manual hierarchy construction (do NOT confuse with `community_multilevel()` which is Louvain, not Leiden)
5. For each community: auto-generate a label from the top 3-5 concepts by frequency
6. Diff against existing communities — update, create, or prune as needed
7. Link chunks to communities via `chunk_communities` based on concept membership

**Incremental behavior**: When a single document is added, most communities remain stable. Leiden scales to millions of nodes (per library docs); for typical org graphs (hundreds to low thousands of concepts), full re-run is under 1 second and is the recommended approach. For very large orgs, `leidenalg` supports `is_membership_fixed` to freeze memberships for existing nodes and only optimize placement of new ones ([advanced docs](https://leidenalg.readthedocs.io/en/stable/advanced.html)). Research on true incremental Leiden exists ([arXiv:2601.08554](https://arxiv.org/abs/2601.08554), "HIT-Leiden") but is not yet in the library.

**Antipattern to avoid**: Do not use raw modularity optimization (`ModularityVertexPartition`) — it has a well-known **resolution limit** that makes small communities invisible in large networks. Always use `RBConfigurationVertexPartition` or `CPMVertexPartition` with explicit resolution.

### 4. Community-Aware Retrieval

Replaces the current flat vector search in process discovery and enhances chat RAG.

**For process discovery** (`semantic_document_search` in `context.py`):
1. Given a domain query (e.g., "quote management"), embed the query
2. Identify relevant communities by comparing query concepts against community member concepts
3. Retrieve chunks from those communities first (community-filtered vector search)
4. Fall back to global vector search for remaining top-k slots
5. Return chunks with community context attached

**For chat RAG** (`build_chat_context` in `chat/context.py`):
1. Same approach but with the user's message as the query
2. Community labels provide additional context to the LLM: "These chunks come from the 'Quote-to-Cash' topic cluster"

### 5. Incremental Amendment Notifications

After a new document is indexed and communities are updated:

1. Query `process_document_sources` for processes linked to the same communities
2. Also query processes whose descriptions have high vector similarity to the new document's chunks
3. Compile a list of potentially affected processes
4. Store a notification record (new `process_notifications` or similar) linking the new document to affected processes
5. Surface in the UI: "Document X may affect these processes: [list]. Re-run discovery?"

No automatic changes to process data. User-initiated re-analysis only.

### 6. Delete & Disk Cleanup

Enhanced delete flow:

1. Load document record, verify org ownership
2. Delete file from disk (`storage_path`)
3. Delete document record (cascades to chunks via `ON DELETE CASCADE`, which cascades to `chunk_communities`)
4. Decrement concept frequencies; remove concepts with frequency = 0
5. Decrement co-occurrence weights; remove edges with weight = 0
6. Re-run community detection if concept graph changed significantly (threshold: >5% of concepts affected)
7. Return 204

**pgvector maintenance after delete**: HNSW index graph is repaired during PostgreSQL's normal autovacuum — no manual REINDEX needed for single-document deletes ([pgvector issue #335](https://github.com/pgvector/pgvector/issues/335)). For bulk deletes (many documents at once), consider: (a) wrap in a single transaction so readers don't see intermediate states, (b) run `VACUUM document_chunks` after the transaction, or (c) for very large bulk ops (>10% of total chunks), drop the HNSW index, vacuum, then rebuild — this can be faster than incremental vacuum on large tables ([pgvector issue #450](https://github.com/pgvector/pgvector/issues/450)).

### 7. Smart Document Library (Frontend)

**Page location**: New route `/documents` in the main app navigation.

**Components**:

- **Upload zone**: Drag-and-drop area + file picker button. Supports multiple files. Shows upload progress per file.
- **Document list**: Paginated table with columns: filename, status (badge), size, upload date, uploader, topics (community labels), chunk count, tags. Sortable and filterable.
- **Document detail panel**: Slide-over or modal showing: full metadata, list of communities/topics this doc contributes to, list of business processes derived from this doc (provenance), chunk preview, tag editor.
- **Search**: Full-text search across document filenames and semantic search across content.
- **Bulk actions**: Select multiple docs for bulk delete or bulk tag.
- **Status indicators**: Real-time status updates via polling or SSE for documents being processed.

---

## Storage Model: Phased Hybrid

### Phase 1 (This Spec)
Direct upload only. Files stored on disk under `uploads/{org_id}/`. All parsing, chunking, embedding happens on our infrastructure.

### Phase 2 (Future Spec)
Add `source_type` enum to Document model: `upload | confluence | sharepoint | gdrive | s3`. Add `source_url`, `source_id`, `last_synced_at` fields. Implement `DocumentSource` abstraction (adapter pattern like LangChain's BaseLoader). Connectors fetch content, then feed into the same parse -> chunk -> embed -> concept extract pipeline.

### Phase 3 (Future Spec)
Webhook/polling sync for external sources. Permission-aware retrieval (filter results by user's access in the source system). Sync status dashboard.

---

## Dependencies

### Python Packages (New)
- `spacy` + `en_core_web_sm` model — noun phrase extraction (upgrade to `en_core_web_md` if extraction quality is insufficient on business documents)
- `leidenalg` — community detection (wraps C implementation, requires `igraph` as dependency). Preferred over `igraph.community_leiden()` for access to `resolution_profile()`, `is_membership_fixed`, and `aggregate_partition()` for hierarchy.
- `igraph` — graph data structure for loading co-occurrence graph into Leiden
- No new infrastructure services required

### Existing Infrastructure (Unchanged)
- PostgreSQL + pgvector — all new tables live here
- Celery + Redis — task queue for vectorization
- Gemini API — embeddings (unchanged)

### Optional Future Dependency
- `apache-age` PostgreSQL extension — if we want Cypher query support for graph traversal. Not required for Phase 1; recursive CTEs handle the needed queries.

---

## Antipatterns & Implementation Warnings

Compiled from research across Microsoft GraphRAG OSS, spaCy maintainer discussions, pgvector issue threads, OHRBench, and production RAG literature.

### Parsing & Chunking

- **Do not chunk before layout reconstruction.** Tables, lists, and structured content must be identified and preserved before chunking. Naive "flatten to text" chunking destroys row/column bindings — retrieval returns orphan numbers without headers. Our existing parser (unstructured) handles this for PDF/DOCX, but validate table output quality per MIME type.
- **Do not use one chunking strategy for all MIME types.** PDFs with scanned images, digital PDFs, HTML, and DOCX have different structure. The adaptive chunker (256/512/1024) is a good start; ensure MIME-type-specific parsing feeds correctly into it.
- **Overlap does not fix destroyed structure.** Token overlap helps with split-mid-thought issues but does not restore relational structure (tables, nested lists) that was already flattened.
- **OCR noise cascades silently.** Per OHRBench ([arXiv:2412.02592](https://arxiv.org/abs/2412.02592)), semantic noise from OCR errors and formatting noise from non-uniform table/formula extraction degrade both retrieval and generation with no stack traces. Add ingestion quality gates: empty-extract rate, token-drop ratio vs source bytes, table detection coverage.

### NLP Concept Extraction

- **spaCy noun chunks vary across models for the same input.** Parser errors differ between `sm`/`md`/`lg`; results are sensitive to capitalization and punctuation ([spaCy issue #4356](https://github.com/explosion/spaCy/issues/4356)). Pin the model version and do not compare concept graphs built with different models.
- **Do not treat noun chunks as ground truth concepts.** They are a heuristic starting point. Domain-specific terms, acronyms, and multi-word expressions may be missed or split incorrectly. Consider a domain-specific stoplist and an acronym expansion table.
- **Synonym collision**: "Sales Manager", "sales manager", and "Sales Mgr" should resolve to one concept. GraphRAG uses UPPERCASE normalization which handles case but not abbreviations. For Phase 1, uppercase is sufficient; future: add embedding-similarity-based concept merging.

### Co-occurrence Graph

- **Do not use document-wide co-occurrence windows.** They produce dense, uninformative graphs where every concept connects to every other concept. Use chunk-level (within-chunk) windows.
- **Raw co-occurrence counts bias toward globally frequent terms.** Always apply PMI weighting. GraphRAG's implementation explicitly notes PMI has a bias toward low-frequency pairs — mitigate with minimum co-occurrence threshold (>= 2-5 before PMI).
- **High-frequency "stop-concepts" become hubs.** Generic business terms ("process", "system", "data", "team") will dominate the graph. Apply per-node degree caps or k-core filtering after PMI.

### Community Detection

- **Do not use `ModularityVertexPartition`** for Leiden — it has a well-known resolution limit that makes small communities invisible in large networks. Use `RBConfigurationVertexPartition` or `CPMVertexPartition` with explicit resolution parameter.
- **Do not confuse `igraph.community_multilevel()` (Louvain) with Leiden.** They are different algorithms; Louvain can produce disconnected communities.
- **Singleton communities** (one concept alone) are a signal that the concept is disconnected or the resolution is too high. Filter or merge them.

### Embeddings & Vector Search

- **Never mix embedding model versions in the same queryable index.** This causes silent retrieval quality degradation with no errors. Track `embedding_model` per document and enforce consistency.
- **Multi-tenant filtered ANN can under-return results.** When filtering by `org_id` on a shared HNSW index, high-selectivity filters may return fewer than `top_k` results. pgvector added iterative index scans to handle this ([pgvector issue #259](https://github.com/pgvector/pgvector/issues/259)). Benchmark recall@k under realistic tenant-filtered conditions as corpus grows.
- **For the largest tenants, partitioning may be needed.** If one org has 10x more chunks than others, evaluate table partitioning by `org_id` or per-tenant HNSW indexes.

### Provenance

- **Do not rely on LLM-generated citations as the system of record.** Models hallucinate citations at high rates ([GhostCite, arXiv:2602.06718](https://arxiv.org/abs/2602.06718)). Capture provenance at the retriever layer — persist the set of chunk IDs and their content hashes that were placed into the LLM context window.
- **Store `content_hash_at_retrieval_time` on provenance edges.** Without this, if a chunk is later re-indexed (chunker change, model upgrade), the provenance record points to content that no longer matches what the LLM saw.

### Observability

- **RAG fails without exceptions.** Plausible answers, gradual latency creep, "related but wrong" chunks, model ignoring context — none of these produce stack traces. Implement per-stage tracing (parse, chunk, embed, concept-extract, community-detect, retrieve, generate) and maintain a golden query set for regression testing retrieval quality.

---

## Graph Query Strategy

For Phase 1, **recursive CTEs over adjacency tables** (not Apache AGE) for all graph queries. Rationale:

- Our graph queries are bounded: concept neighborhood (1-2 hops), community membership, provenance chains (tree/DAG structure)
- Recursive CTEs handle these well with proper depth caps and per-level `DISTINCT`
- Apache AGE requires a custom PostgreSQL extension install — many managed Postgres offerings do not support it
- AGE's advantage (Cypher syntax, complex declarative traversals) is overkill for our Phase 1 query patterns

**If needed later**: AGE v1.7.0 (Jan 2026) supports PG18 with RLS and id-index improvements. The team is small and releases are not on a fixed schedule ([roadmap discussion](https://github.com/apache/age/discussions/2305)). Evaluate if/when we need variable-length path queries or complex pattern matching.

**Antipattern**: Standard recursive CTEs re-traverse shared descendants in diamond-shaped graphs, causing exponential work. For community traversal this is rarely an issue (tree structure), but for concept neighborhood queries on dense subgraphs, use application-side BFS with a visited set rather than pure SQL recursion.

---

## What This Does NOT Cover

- External source connectors (Confluence, SharePoint, etc.) — Phase 2
- Full GraphRAG with LLM-based entity extraction — replaced by LazyGraphRAG NLP approach
- Neo4j or any external graph database — stays in PostgreSQL
- Auto-suggesting or auto-applying process amendments — design target is notify-only
- Document version history — future enhancement
- Impact analysis on delete ("these processes will be affected") — future enhancement, enabled by provenance tracking
- Chat file upload — separate concern, excluded per existing chat design spec

---

## Relationship to Josh's arcflare-local-demo

| Josh's Implementation | This Design | Notes |
|---|---|---|
| SQLite catalog | PostgreSQL `documents` table | Already in place |
| SHA-256 dedup | SHA-256 `content_hash` column | Adopting from Josh |
| File watcher (watchdog) | Not included | Web upload replaces directory watching |
| spaCy `en_core_web_trf` NER | spaCy `en_core_web_sm` noun phrases | Lighter model, different extraction strategy (LazyGraphRAG-aligned) |
| Neo4j knowledge graph | PostgreSQL concept/community tables | Same logical structure, different storage |
| Neo4j vector index (384d) | pgvector (3072d Gemini) | Already in place, higher dimension |
| Connection agent (rapidfuzz + Claude) | Community detection (Leiden) | Algorithmic vs. LLM-based entity resolution |
| Synthesis agent (Claude Opus) | Existing process discovery pipeline | Already built differently |
| CLI interface | Web API + Smart Document Library UI | Multi-tenant web app |

---

## Success Criteria

1. Uploading a duplicate file (same content hash) returns the existing document without re-processing
2. Concept extraction produces meaningful noun phrases from uploaded documents
3. Community detection groups related concepts into coherent topic clusters
4. Community-filtered vector search returns more relevant chunks than flat vector search for multi-hop queries
5. Document detail view shows which communities and processes a document contributes to
6. Deleting a document removes the file from disk, all chunks, vectors, and concept associations
7. Uploading a document that overlaps with existing process topics triggers a notification identifying affected processes
8. All new tables are properly scoped by `org_id` for multi-tenant isolation
