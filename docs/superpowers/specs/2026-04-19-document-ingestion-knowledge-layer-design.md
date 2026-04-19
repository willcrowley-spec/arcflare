# Document Ingestion & Knowledge Layer Design

**Date**: 2026-04-19
**Status**: Approved
**Scope**: Enhanced document ingestion pipeline, LazyGraphRAG-style knowledge layer, Smart Document Library UI, incremental amendment notifications

---

## Context & Problem Statement

Arcflare's current document pipeline handles the basics — upload, parse, chunk, embed, store in pgvector — but lacks several capabilities needed for production-quality process discovery:

1. **No deduplication**: Re-uploading the same file re-processes it entirely.
2. **No structured knowledge extraction**: Documents are chunked and embedded but not analyzed for entities, concepts, or relationships. Process discovery relies on flat vector search, which benchmarks at 68-72% accuracy on multi-hop queries vs. 83-87% with graph-enhanced retrieval (Microsoft Research, 2025-2026).
3. **No provenance tracking**: No record of which documents informed which business processes.
4. **No document management UI**: API routes exist but no frontend page.
5. **No incremental updates**: Adding a document requires re-running the full discovery pipeline to incorporate its knowledge.
6. **Incomplete delete**: Removing a document deletes DB rows but leaves the file on disk.

Josh's `arcflare-local-demo` repo implemented a full pipeline (parse -> NER -> chunk -> embed -> Neo4j knowledge graph -> connection agent -> synthesis agent) but targeted a single-tenant local CLI. This design adapts the relevant patterns for our multi-tenant web platform, informed by 2026 industry research.

---

## Research Summary

### Sources Consulted

- **Google Vertex AI RAG Engine** — data connector architecture, layout-aware chunking, dedup patterns
- **Microsoft GraphRAG / LazyGraphRAG** (Microsoft Research, 2025-2026) — community detection, deferred LLM usage, benchmark comparisons
- **LangChain document loader architecture** — BaseLoader abstraction, Confluence/SharePoint connectors
- **Particula Tech** — incremental RAG update patterns, delta indexing, metadata versioning
- **Everstone AI** — GDPR vector deletion compliance, delta-sync indexes
- **DBI Services** — event-driven embedding refresh, pgvector lifecycle management
- **Apache AGE / Piggie benchmarks** — PostgreSQL graph extension, 25x speedup over Neo4j on concurrent queries

### Key Findings

| Finding | Source | Impact |
|---------|--------|--------|
| GraphRAG improves multi-hop query accuracy by 15-19% over vector-only | Microsoft Research | Directly benefits process discovery |
| LazyGraphRAG achieves comparable quality at 0.1% of GraphRAG indexing cost | Microsoft Research | Eliminates cost barrier to graph-enhanced retrieval |
| NLP noun phrase extraction + community detection replaces expensive LLM entity extraction | LazyGraphRAG paper | Indexing cost stays identical to current vector pipeline |
| Apache AGE adds Cypher graph queries to PostgreSQL; benchmarks beat Neo4j | Piggie v0.5.0 | No new infrastructure needed |
| Content hashing reduces re-indexing costs by 80-95% | Particula Tech, multiple | Prevents wasted processing on unchanged content |
| Cascade delete in pgvector cleanly removes embeddings (no "ghost vectors") | Everstone AI, pgvector docs | Our FK cascade already handles this correctly |
| Enterprise RAG systems universally adopt hybrid storage (upload + connectors) | Google, LangChain, Katonic AI | Validates phased hybrid approach |

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
| weight | INTEGER | co-occurrence count |
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
| relevance_score | FLOAT | how relevant the doc was to this process |
| created_at | TIMESTAMPTZ | |

#### Modified Tables

**`documents`** — add columns:

| Column | Type | Notes |
|--------|------|-------|
| content_hash | VARCHAR(64) | SHA-256 hash for dedup |
| concept_count | INTEGER | number of concepts extracted, default 0 |
| community_ids | JSONB | communities this document contributes to |

**`document_chunks`** — add column:

| Column | Type | Notes |
|--------|------|-------|
| concept_ids | JSONB | concepts extracted from this chunk |

---

## Component Designs

### 1. Content Hashing & Dedup

At upload time, before writing to disk:

1. Stream the file through SHA-256 while writing to a temp buffer
2. Query `documents` for matching `content_hash` within the same `org_id`
3. If match found and status is `indexed`: return the existing document (skip re-processing)
4. If match found but status is `error`: allow re-upload (overwrite)
5. If no match: proceed with normal upload flow

The hash is computed on raw file bytes, not parsed content, so format differences (e.g., re-exported PDF) are treated as new documents.

### 2. NLP Concept Extraction

Runs as step 4 in the Celery vectorization task, after chunking and before embedding.

**Extraction method**: spaCy noun phrase extraction using `en_core_web_sm` (small model, fast, no GPU needed). This aligns with LazyGraphRAG's approach of using lightweight NLP rather than LLM-based entity extraction.

For each chunk:
1. Run spaCy NLP pipeline on chunk text
2. Extract noun phrases (noun chunks)
3. Normalize: lowercase, strip articles/determiners, collapse whitespace
4. Filter: remove phrases < 2 characters or > 100 characters, remove pure stopword phrases
5. Upsert into `concepts` table (increment frequency if exists)
6. For each pair of concepts co-occurring in the same chunk, upsert into `concept_cooccurrences` (increment weight)
7. Store concept IDs in `document_chunks.concept_ids`

**Token budget**: spaCy `en_core_web_sm` runs locally, no API calls. Processing cost is CPU-only, ~50ms per chunk on typical hardware.

### 3. Community Detection

Runs as step 6, after concept extraction completes for all chunks in the document.

**Algorithm**: Leiden community detection (via `leidenalg` Python library or `igraph` built-in). Operates on the concept co-occurrence graph for the org.

1. Load concept co-occurrence graph for the org from `concept_cooccurrences`
2. Run Leiden algorithm with resolution parameter tuned for the graph size
3. Extract hierarchical community structure (multiple levels)
4. For each community: auto-generate a label from the top 3-5 concepts by frequency
5. Diff against existing communities — update, create, or prune as needed
6. Link chunks to communities via `chunk_communities` based on concept membership

**Incremental behavior**: When a single document is added, most communities remain stable. Leiden is fast enough to re-run on the full org graph (typical org: hundreds to low thousands of concepts, runs in <1 second). For very large orgs, we can implement incremental community updates.

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
3. Delete document record (cascades to chunks, chunk_communities, concept associations)
4. Decrement concept frequencies; remove concepts with frequency = 0
5. Decrement co-occurrence weights; remove edges with weight = 0
6. Re-run community detection if concept graph changed significantly (threshold: >5% of concepts affected)
7. Return 204

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
- `spacy` + `en_core_web_sm` model — noun phrase extraction
- `leidenalg` or `igraph` — community detection algorithm
- No new infrastructure services required

### Existing Infrastructure (Unchanged)
- PostgreSQL + pgvector — all new tables live here
- Celery + Redis — task queue for vectorization
- Gemini API — embeddings (unchanged)

### Optional Future Dependency
- `apache-age` PostgreSQL extension — if we want Cypher query support for graph traversal. Not required for Phase 1; recursive CTEs handle the needed queries.

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
