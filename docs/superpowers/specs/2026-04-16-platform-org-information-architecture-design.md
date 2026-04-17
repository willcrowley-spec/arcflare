# Platform vs. Organization Information Architecture — Design Spec

**Date:** 2026-04-16
**Status:** Approved
**Approach:** Platform-first migration (build platform detail page, relocate content, clean up Organization and Analysis)

---

## Problem Statement

The metadata catalog on the Analysis page is Salesforce-native, surfaces low-value detail (field counts, meaningless status labels, per-object sync timestamps), and conflates platform-specific data with cross-platform analysis. The Organization page mixes aggregate company intelligence with platform-specific metrics (Salesforce licensing, role distribution). Neither page is structured to support multiple connected platforms.

This redesign establishes a clear boundary: **what lives at the platform level** (metadata, licensing, adoption, roles) vs. **what lives at the organization aggregate level** (company identity, cross-platform spend, analysis configuration). The Analysis page is stripped back to connection management, reserving space for future cross-platform ecosystem intelligence.

---

## 1. Platform Detail Page

**Route:** `/platforms/:connectionId`
**Access:** Click a connection card on the Analysis page.

### 1.1 Header

- Platform name + icon (e.g., "Salesforce" with SF badge)
- Connection status (connected / disconnected)
- Instance URL / org ID
- Last sync timestamp (connection-level, not per-object)
- Actions: "Sync Now", "Re-authenticate"

### 1.2 KPI Row

Top-level summary cards:

| KPI | Source |
|-----|--------|
| Total Objects | Count of `metadata_objects` for this connection |
| Total Automations | Count of `metadata_automation` for this connection |
| Total Code Assets | Count of `metadata_components` where category = code |
| Total Records | Sum of `record_count` across all objects |

### 1.3 Data Objects Table

The primary interactive surface. Users classify objects here.

**Columns:**

| Column | Source | Notes |
|--------|--------|-------|
| Entity | `label` + `api_name` | Platform-agnostic label |
| Type | `object_type` | "Standard Object", "Custom Object" for SF; "Table" for HubSpot, etc. |
| Classification | `classification` | Editable tag: Operational / Configuration / Empty / Deprecated |
| Records | `record_count` | Integer, no field count |
| Velocity | `velocity_score` | Visual indicator (hot/warm/cold or numeric) |
| Automations | Count of related `metadata_automation` rows | Replaces boolean flags |

**Behaviors:**

- Filterable by classification (show/hide Empty, Deprecated, etc.)
- Empty objects (0 records) rendered with muted row styling
- Clicking the classification tag opens an inline selector to override
- Override persists as `classification_source = 'manual'` and is preserved across re-syncs

### 1.4 Automations Summary

KPI cards showing counts by automation type. For Salesforce: Flows, Triggers, Validation Rules. For future platforms: normalized labels. Active vs. inactive breakdown. No full browsable table — the raw data is vectorized for AI analysis, not for human browsing.

### 1.5 Code Summary

Count of code assets (Apex classes for SF, equivalent for other platforms). Split: managed package code vs. custom code. No browsable table.

### 1.6 Licensing

Relocated from Organization page. License types, utilization bars, seat counts. Rendered identically to current implementation, just on a different page.

### 1.7 Platform Adoption

Relocated from Organization page. Login trends, active user counts, adoption charts.

### 1.8 Role & Profile Distribution

Relocated from Organization page. Existing charts and breakdowns.

### 1.9 Installed Packages

Relocated from Analysis tabs. Package list with version, namespace, managed status.

---

## 2. Backend Changes

### 2.1 Schema: `metadata_objects`

**Add columns:**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `classification` | `String(20)` | `null` | `operational`, `configuration`, `empty`, `deprecated` |
| `classification_source` | `String(10)` | `'auto'` | `auto` or `manual` |
| `velocity_score` | `Float` | `0.0` | Computed from `RecordTelemetry` deltas |

**Drop columns:**

| Column | Reason |
|--------|--------|
| `has_triggers` | Replaced by automation count join |
| `has_flows` | Replaced by automation count join |
| `has_validation_rules` | Replaced by automation count join |
| `last_synced_at` | Connection-level timestamp is sufficient |

**Migration:** Destructive is acceptable — drop and recreate. No data migration needed.

### 2.2 Schema: Organization — `analysis_config`

Add `analysis_config` JSON column to the Organization model. JSON is appropriate here — the keys are well-defined, the values are simple scalars, and a dedicated table would over-normalize for 6 config keys.

**Initial keys:**

```json
{
  "velocity_window_days": 30,
  "classification_threshold": 0.1,
  "min_records_for_vectorization": 1,
  "embedding_provider": "default",
  "vector_store_provider": "default",
  "llm_provider": "default"
}
```

- First three are functional and exposed in the Organization page UI.
- Last three are placeholders — read by backend code, always resolve to built-in provider. Not exposed in UI yet. The seam exists so future BYO adapters don't require restructuring.

### 2.3 Classification Heuristic

Runs during sync, after telemetry computation. Only applied when `classification_source` is `auto` or `null`:

```
if record_count == 0:
    classification = "empty"
elif velocity_score > org.analysis_config.classification_threshold:
    classification = "operational"
else:
    classification = "configuration"
```

The `classification_threshold` is read from the org's `analysis_config`. Default `0.1` means "any meaningful delta in the velocity window."

Objects where `classification_source == 'manual'` are never overwritten by the heuristic.

### 2.4 Velocity Computation

After `RecordTelemetry` snapshot during sync:

1. Query `RecordTelemetry` rows for the object within the trailing `velocity_window_days` (from org config).
2. Sum `created_count_delta + modified_count_delta` across the window.
3. Normalize (TBD — simple sum may suffice initially; can add log-scaling or percentile ranking later).
4. Write result to `metadata_objects.velocity_score`.

### 2.5 Vectorization Gating

In the vectorization worker, the query that selects objects for vectorization adds:

```sql
WHERE record_count > 0
  AND (classification IS NULL OR classification NOT IN ('empty', 'deprecated'))
  AND record_count >= org.analysis_config.min_records_for_vectorization
```

Objects that fail this filter are never sent to the embedding pipeline.

### 2.6 New API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `PATCH` | `/api/v1/metadata/objects/{object_id}/classification` | Set classification + mark `classification_source = 'manual'` |
| `GET` | `/api/v1/organizations/{org_id}/settings` | Return `analysis_config` |
| `PATCH` | `/api/v1/organizations/{org_id}/settings` | Update `analysis_config` keys |

### 2.7 Sync Phase Cleanup

**Remove entirely:**
- `reports` phase — no longer pulling report/dashboard metadata
- Remove report/dashboard rows from `metadata_components` insertion logic
- Remove `pull_reports_dashboards` (or equivalent) from sync pipeline

**Merge into single phases:**
- `flows` + `triggers` + `validation_rules` → single `automations` progress phase (backend still pulls them separately via Tooling API, but Redis progress tracker shows one phase)
- `fields` progress phase collapsed into `objects` phase (fields are pulled during object describe, the separate progress tick is artificial)

**Updated progress phases:**

```python
PHASES = [
    "objects",        # includes field extraction
    "automations",    # flows + triggers + validation rules
    "code",           # apex classes
    "permissions",
    "ui_components",  # layouts, flexipages (no reports/dashboards)
    "installed_packages",
    "licensing",
    "user_velocity",
    "entities",
    "vectorization",
]
```

### 2.8 Response Schema Updates

**`MetadataObjectResponse`** — add `classification`, `classification_source`, `velocity_score`. Remove `has_triggers`, `has_flows`, `has_validation_rules`, `last_synced_at`. Add `automation_count` (computed via join or subquery).

**`MetadataSummary`** — update to reflect new phase structure. Remove report counts.

---

## 3. Organization Page — Company Intelligence Card

### 3.1 Company Profile

Inline-editable card (Notion-style property editing — read state and edit state feel like the same UI, not a separate form page).

| Field | Type | Notes |
|-------|------|-------|
| Company Name | Text | Single value |
| Domains / Websites | Multi-value text | Add/remove chips |
| Industry | Searchable select | Standard industry list |
| Estimated Headcount | Number | Manual entry; auto-enriched in future |
| Estimated Annual Revenue | Currency | Manual entry; auto-enriched in future |
| Key Contacts | Name + Role list | Simple repeatable row |

Form quality is critical — use `impeccable` skill for the interaction design. No scattered "Edit" buttons with raw input fields.

### 3.2 Connected Platforms

Compact card row showing each connected platform:
- Platform name + icon
- Connection status
- Estimated annual spend (per-platform)
- Link to `/platforms/:connectionId`

Above the cards: **Aggregate annual spend** across all platforms.

### 3.3 Analysis Settings

Exposed tuning variables:

| Setting | Input Type | Default | Description |
|---------|-----------|---------|-------------|
| Velocity Window | Number (days) | 30 | Lookback period for velocity computation |
| Classification Threshold | Number (float) | 0.1 | Velocity score above which an object is "operational" |
| Min Records for Vectorization | Number | 1 | Objects below this count are skipped |

Provider settings (`embedding_provider`, `vector_store_provider`, `llm_provider`) are stored in `analysis_config` but not rendered in the UI. They're read by backend code and default to `"default"`.

### 3.4 Re-analyze Action

A "Re-analyze" button in the Analysis Settings section. When clicked, it triggers a lightweight backend job that:

1. Recomputes `velocity_score` for all objects across all connections using the updated `velocity_window_days` — querying existing `RecordTelemetry` data, no Salesforce API calls.
2. Recomputes `classification` for all objects where `classification_source == 'auto'`, using the updated `classification_threshold` and `min_records_for_vectorization`.
3. Does **not** re-sync metadata from the platform.
4. Does **not** re-run vectorization. Vectorization gating applies naturally on the next sync. If the user wants to re-vectorize after changing settings, they trigger a sync explicitly.

**API endpoint:** `POST /api/v1/organizations/{org_id}/reanalyze`

The button shows a brief progress state ("Re-analyzing...") and refreshes the connected platform KPIs on completion. If the user is viewing a platform detail page afterward, the updated classifications and velocity scores are reflected immediately.

### 3.5 Content Removed from Organization Page

All of the following relocate to the Platform Detail page:
- Org Hierarchy
- Salesforce Licensing → "Licensing"
- Platform Adoption
- Role & Profile Distribution
- User Velocity / Classification charts
- Salesforce-specific Business Profile fields

---

## 4. Analysis Page — Cleanup

### 4.1 What Stays

- **Platform Sources component** — connection cards with sync, re-auth, and click-through to `/platforms/:connectionId`
- **Sync progress panel** — shows progress during active sync
- **Connect Platform modal** — for adding new connections

### 4.2 What Gets Removed

- Entire metadata catalog (Objects, Automations, Apex, Reports, Permissions, Packages tabs)
- Metadata summary KPI cards (object count, field count, automation count)
- Type filter dropdown (ALL / OBJECTS / etc.)
- All related hooks, state, and column definitions for the catalog tabs

### 4.3 Post-Cleanup State

The page is intentionally sparse: connection management + empty canvas for future cross-platform ecosystem analysis (to be designed separately).

---

## 5. Skill Updates

Update the following skill files with a "consider configurability" heuristic:

> "When implementing business logic with hardcoded thresholds or constants that affect analysis quality, output fidelity, or could reasonably vary by customer, flag whether the value should be an org-level configuration variable. Prefer config over constants. Check if the value belongs in `analysis_config`."

**Target skills:**
- `salesforce-development/SKILL.md`
- `react-quality/SKILL.md`

---

## 6. Platform-Agnostic Naming

All UI labels and backend category names should be platform-neutral:

| Salesforce Term | Platform-Agnostic Label |
|----------------|------------------------|
| Objects | Data Objects / Entities |
| Flows, Triggers, Validation Rules | Automations |
| Apex Classes | Code |
| Permission Sets, Profiles | Permissions |
| Installed Packages | Packages |
| Reports & Dashboards | *(removed)* |

When HubSpot or other platforms are added, their metadata types map into these same categories. The platform detail page uses the agnostic labels; platform-specific terminology can appear in tooltips or secondary text if needed.

---

## 7. Data & Migration

Existing data can be cleared. No backward-compatible migration is required. The Alembic migration for this change can drop and recreate affected tables/columns.

---

## 8. UI Quality: Impeccable Skill

All frontend work in this spec must use the `impeccable` design skill suite. Specifically:

- **Platform Detail Page:** Use `/polish` on the header, KPI row, and data objects table after initial implementation. The classification inline-edit interaction, velocity indicators, and muted empty-row styling should follow `impeccable/reference/interaction-design.md` and `impeccable/reference/craft.md`.
- **Organization Page — Company Profile:** Use `/polish` on the inline-editable card form. The Notion-style property editing pattern must follow `impeccable/reference/interaction-design.md` for focus states, transitions, and input affordances. Multi-value domain chips and the searchable industry select follow `impeccable/reference/ux-writing.md` for microcopy.
- **Analysis Settings form:** The tunable config inputs (velocity window, threshold, min records) and the Re-analyze button follow `impeccable/reference/spatial-design.md` for layout and `impeccable/reference/typography.md` for label hierarchy.
- **Analysis Page cleanup:** The sparse post-cleanup state needs a quality empty state — not a blank page. Use `impeccable/reference/ux-writing.md` for the empty state copy.

---

## 9. Out of Scope

- Cross-platform ecosystem analysis on the Analysis page (separate brainstorm)
- External enrichment pipeline for Organization (LinkedIn, web scraping, semantic search)
- BYO provider UI (vector store, embedding model, LLM selection)
- Full browsable tables for Automations, Code, Permissions on the platform detail page
