# Arcflare Backlog

## Recently Completed

### Document Pipeline Simplification
Removed GraphRAG community detection from document processing. Replaced with per-document LLM summary, surfaced concepts + chunks with contextual prefixes in UI, added processing phase progress indicator.

### Document Upload Progress Indicator
Added `processing_phase` field to Document model. Frontend polls and renders a 5-step progress bar (downloading → parsing → embedding → extracting concepts → summarizing).

## Backlog

### Remove v1 Discovery Pipeline Dead Code
**Priority:** Low | **Area:** Backend  
`run_stage1` through `run_stage7` in `discovery.py` (~1200 lines) are deprecated and never called. Currently marked with a deprecation banner. Should be fully removed once v2 is stable in production.

### N+1 Query in Community Summarizer
**Priority:** Medium | **Area:** Backend  
`summarize_metadata_communities` issues per-community queries for children. Should batch-load all parent→child relationships upfront.

### Clean Up Unused Document Community Code
**Priority:** Low | **Area:** Backend  
`documents/communities.py`, `link_chunks_to_communities`, `summarize_document_communities`, and `compute_pmi_weights` are no longer called from the worker. Can be removed once document communities are confirmed unnecessary in production.

---
_Last updated: 2026-04-20_
