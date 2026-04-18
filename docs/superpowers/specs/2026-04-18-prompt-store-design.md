# Prompt Store & DSPy Optimization — Design Spec

**Date:** 2026-04-18
**Status:** Approved

## Problem

All 9 LLM operations in Arcflare have prompts hardcoded as Python f-strings across 6 backend files. Changing any prompt requires a code change and deploy. There is no way to:
- Edit prompts at runtime without deploying
- Let org admins customize prompts for their organization
- Version or audit prompt changes
- Automatically optimize prompts using data-driven methods

## Solution Overview

Two-layer architecture:

1. **Prompt Store** — A database-backed prompt management system with block-based composition, copy-on-write per-org overrides, version history, and an admin UI under Settings. Prompts move from code into the database. The app fetches and assembles them at runtime.

2. **DSPy Optimization (Phase 1 — platform operator only)** — An offline optimization pipeline using Stanford's DSPy framework. Extracts training data from Langfuse traces, runs optimizers (MIPROv2, BootstrapFewShot) against prompt blocks, and writes results as draft versions in the store for the operator to review and promote.

## Data Model

### `prompt_block` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `operation_id` | VARCHAR(64) | Key from `MODEL_OPERATIONS` (e.g., `"chat"`, `"discovery_domain"`) |
| `block_type` | VARCHAR(64) | e.g., `"identity"`, `"rules"`, `"protocol"`, `"workflow"`, `"examples"` |
| `org_id` | UUID FK nullable | `NULL` = system default, non-null = org override |
| `content` | TEXT | The prompt text. May contain interpolation variables like `{agent_name}` |
| `version` | INT | Starts at 1. Incremented on each PUT. Previous version's status is set to `"archived"` before the new active row is created. |
| `status` | VARCHAR(16) | `"active"`, `"draft"`, `"archived"` |
| `forked_from_id` | UUID FK nullable | Points to the system default block this was forked from |
| `created_by` | UUID FK nullable | User who created/edited |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Unique constraint:** `(operation_id, block_type, org_id)` where `status = 'active'` — only one active block per operation + type + org.

### `prompt_optimization_run` table (DSPy)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `operation_id` | VARCHAR(64) | Which operation was optimized |
| `block_type` | VARCHAR(64) | Which block was optimized |
| `optimizer` | VARCHAR(32) | `"miprov2"`, `"bootstrap_few_shot"` |
| `metric_name` | VARCHAR(128) | What was measured (e.g., `"json_parse_rate"`, `"schema_compliance"`) |
| `metric_score_before` | FLOAT | Baseline score |
| `metric_score_after` | FLOAT | Optimized score |
| `result_block_id` | UUID FK nullable | Points to the draft `prompt_block` created |
| `status` | VARCHAR(16) | `"running"`, `"completed"`, `"failed"` |
| `created_at` | TIMESTAMP | |
| `completed_at` | TIMESTAMP nullable | |

### Copy-on-Write Pattern

- **System defaults:** `org_id = NULL`. Managed by platform operator. Seeded from current hardcoded prompts on first migration.
- **Org overrides:** When an org admin edits an editable block, a new row is created with their `org_id` and `forked_from_id` pointing to the system default row.
- **Restore defaults:** Delete the org override row. Resolution falls through to the system default. One operation, no knowledge of the default required.
- **System updates:** When the platform operator updates a system default, orgs that haven't customized that block get the update automatically. Orgs with forks keep their version.

## Block Registry

Defines which blocks exist per operation and whether org admins can edit them.

### Chat (`chat`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `identity` | Agent Identity & Role | Yes | Tone, persona, name |
| `rules` | Communication Rules | Yes | Response length, style |
| `protocol` | Output Protocol | No | JSON schema — breaking this breaks the UI |
| `workflow` | Workflow Steps | Yes | Discovery sequence |
| `examples` | Few-Shot Examples | Yes | Most impactful for behavior tuning |

### Discovery — Domain (`discovery_domain`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Analysis Instructions | Yes | What to look for, how to categorize |
| `protocol` | Output Schema | No | JSON structure |
| `examples` | Examples | Yes | |

### Discovery — Decomposition (`discovery_decomposition`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Decomposition Instructions | Yes | How to break domains into sub-processes |
| `protocol` | Output Schema | No | |
| `examples` | Examples | Yes | |

### Discovery — Synthesis (`discovery_synthesis`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Synthesis Instructions | Yes | Cross-domain gap detection rules |
| `protocol` | Output Schema | No | |
| `examples` | Examples | Yes | |

### Metadata Enrichment (`metadata_enrichment`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Enrichment Instructions | Yes | How to describe platform objects |
| `protocol` | Output Schema | No | |

### Entity Extraction (`entity_extraction`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Single Extraction Instructions | Yes | What entities to extract from a single document |
| `instructions_batch` | Batch Extraction Instructions | Yes | How to extract across multiple documents |
| `protocol` | Output Schema | No | |

### Process Matching (`process_matching`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Matching Instructions | Yes | Disambiguation rules |
| `protocol` | Output Schema | No | |

### Recommendations (`recommendations`)

| Block Type | Label | Editable | Notes |
|-----------|-------|----------|-------|
| `instructions` | Document Generation Instructions | Yes | What to include in process docs |
| `protocol` | Output Schema | No | |
| `examples` | Examples | Yes | |

### Embedding (`embedding`)

No prompt blocks. Uses a dedicated embedding model with no user-authored prompt. Excluded from the operations list in the Settings UI — does not appear in the sidebar.

## Prompt Resolution

When any part of the app needs a prompt:

1. Fetch all active system defaults for the operation (`org_id IS NULL, status = 'active'`)
2. Fetch all active org overrides for the operation (`org_id = <current org>, status = 'active'`)
3. Per block type: org override wins if it exists, else system default
4. Interpolate runtime variables (`{agent_name}`, `{tools_block}`, `{org_context}`, etc.)
5. Stitch blocks together in registry-defined order into the final prompt string
6. Send to LLM — the LLM sees one prompt, unaware of blocks

**Caching:** Resolved blocks are cached per `(operation_id, org_id)` with a 60-second TTL. Cache invalidates on any write to `prompt_block` for that operation + org.

**Available variables per block:** Each block type documents which interpolation variables are available (e.g., `{agent_name}` in identity, `{tools_block}` in the auto-injected section). The UI displays these below the editor.

**Variable validation:** On PUT (save), the backend validates that all required variables for the block type are present in the content. If a required variable is missing (e.g., `{agent_name}` removed from identity), the save returns a 422 with a message listing the missing variables. Optional variables are not enforced. The block registry defines which variables are required vs. optional per block type.

**Identical-to-default detection:** On PUT, if the submitted content is byte-identical to the current system default for that block, no fork is created. The response returns `is_customized: false` and a notice. This prevents accidental forks and keeps the override table clean.

**Fallback-to-code safety net:** During the transition period, if `resolve_prompt_blocks()` finds zero active blocks for an operation (e.g., migration failed or DB is empty), it falls back to the original hardcoded prompt strings. This prevents total LLM failure if seeding goes wrong. The fallback logs a warning via Langfuse so the operator is alerted. Once the prompt store is stable, the fallback can be removed.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/prompts/operations` | List all operations with block types, labels, editability. Powers the Settings UI sidebar. |
| `GET` | `/api/v1/prompts/{operation_id}` | Returns all blocks for that operation, merged (org override wins over default). Each block includes: content, `is_customized`, `is_locked`, available variables. |
| `PUT` | `/api/v1/prompts/{operation_id}/blocks/{block_type}` | Save an org's customization for one block. Creates the copy-on-write fork. Returns 403 if block is locked. |
| `DELETE` | `/api/v1/prompts/{operation_id}/blocks/{block_type}` | Restore defaults — deletes the org's fork for that block. |

All endpoints scoped to the current org via auth. Platform-level system default management uses the same PUT/DELETE with a platform admin role (no org_id in the write). Until a formal role system exists, platform admin access is gated by an environment variable or API key check.

## Settings UI

### Location

New "Prompts" tab on the existing Settings page, alongside the current "Analysis" and "Models" tabs.

### Layout

- **Left column:** Operation list, grouped by `OPERATION_GROUPS` (Metadata Pipeline, Analysis, Discovery Pipeline, Synthesis, Chat Assistant). Click to select.
- **Right column:** Blocks for the selected operation, stacked vertically as cards.

### Block Card

Each card contains:
- **Block label** (e.g., "Agent Identity & Role") as a header
- **Text editor** — simple textarea with monospace font. Disabled with a lock icon and muted styling if the block is not editable.
- **"Customized" badge** — small orange pill visible when the org has overridden that block
- **Restore defaults icon** — `RotateCcw` icon, only visible on customized blocks. Tooltip: "Restore to platform default." Click triggers inline confirmation ("Restore? Yes / No") matching the existing lightweight confirmation pattern.
- **Available variables** — small muted text below the editor listing interpolation variables for that block (e.g., `Available: {agent_name}`)
- **Save button** — per-block, right-aligned, only enabled when content differs from the stored version

### Auto-Injected Context (Read-Only Section)

Below the editable blocks, a collapsed "System Context" section shows what the platform automatically appends to the prompt at runtime. This is read-only — admins cannot edit it, but they can see it to understand the full picture. Contents vary by operation:
- **Chat:** Available tools list, organization settings JSON, anchor context (when applicable), RAG results (when applicable)
- **Discovery:** Organization context JSON, metadata summary, document summary
- **Other operations:** Operation-specific data payloads

Displayed as a muted, collapsible card with a `ChevronDown` toggle and an info tooltip: "These sections are added automatically by the platform and cannot be edited."

### UI States

- **Loading:** Skeleton cards while blocks are fetched. Operation list shows immediately from the registry (client-side); block content shows a shimmer placeholder until the API responds.
- **Save in progress:** Save button shows a spinner and is disabled. On success, a brief green checkmark and "Saved" toast. On 422 (variable validation failure), the missing variables are highlighted in the error message below the textarea.
- **Restore in progress:** After "Yes" confirmation, the card content transitions to the system default with a brief fade. "Customized" badge disappears.
- **Empty state:** If an operation has no blocks (shouldn't happen after seeding, but defensive), show a single card: "No prompt blocks configured for this operation."
- **Error state:** If the GET fails, show an inline error banner with a retry button — not a full-page error.

### Not in v1

- Bulk save across blocks
- Preview compiled prompt
- Drag-and-drop block reordering
- Diff view against system default
- Version history browser

## DSPy Integration (Phase 1)

### Scope

Platform operator only. Not exposed in the org admin UI.

### Flow

1. **Training data:** Extracted from Langfuse traces for the target operation. Traces contain input/output pairs that serve as examples for DSPy optimizers. Minimum ~30 examples recommended.
2. **Trigger:** CLI command or Celery task. Operator specifies operation + block + optimizer.
3. **Optimization:** DSPy runs the selected optimizer (MIPROv2 or BootstrapFewShot) against the current active block content, testing variations and scoring against a defined metric.
4. **Result:** A new `prompt_block` row with `status = 'draft'` and a corresponding `prompt_optimization_run` record tracking the job metadata and scores.
5. **Promotion:** Operator reviews the draft in the Settings UI (visible as a "Suggested improvement" indicator on the block). Promotes by editing the system default to match, or a future "promote" button.

### Metrics (per operation)

| Operation | Candidate Metric |
|-----------|-----------------|
| `chat` | Valid JSON parse rate, schema compliance |
| `discovery_*` | Required field completeness, structural validity |
| `entity_extraction` | Entity recall against labeled set |
| `metadata_enrichment` | Description quality score (LLM-as-judge) |
| `process_matching` | Match accuracy against labeled pairs |
| `recommendations` | Document completeness score |

### Deferred

- Org-admin-triggerable optimization
- Automatic metric selection
- Scheduled recurring optimization runs
- A/B testing between draft and active versions
- Automatic promotion of improvements

## Migration & Seeding

The Alembic migration creates both tables and seeds `prompt_block` with system defaults extracted from the current hardcoded prompt strings. This is a one-time migration — after it runs, the hardcoded strings are no longer used. Existing behavior is preserved exactly.

### Refactoring Scope

All prompt-building functions are refactored to call `resolve_prompt_blocks()` instead of returning hardcoded strings:
- `backend/app/services/chat/context.py` → `build_system_prompt()`
- `backend/app/services/processes/prompts.py` → `build_pass1_prompt()`, `build_pass2_prompt()`, `build_pass3_prompt()`
- `backend/app/services/connectors/describe.py` → `DESCRIBE_PROMPT`
- `backend/app/services/extraction/llm_extract.py` → `EXTRACTION_PROMPT`, `BATCH_PROMPT`
- `backend/app/services/processes/matcher.py` → `_llm_disambiguate()`
- `backend/app/services/recommendations/synthesis.py` → `generate_process_document()`

## Future Considerations (not in scope)

- **Enterprise tier gating:** Prompt customization as a paid feature. Data model supports this (check org tier before allowing PUT).
- **"Platform default updated" indicator:** Show org admins when the system default has changed since their fork.
- **Diff view:** Side-by-side comparison of org override vs. system default.
- **Version history:** Browse and restore previous versions of a block.
- **Org-facing DSPy optimization:** Let org admins trigger optimization scoped to their data.
