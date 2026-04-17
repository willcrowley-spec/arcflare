# Classification System Redesign

**Date:** 2026-04-17  
**Status:** Draft

## Problem

The current classifier uses a single signal — `velocity_score / record_count > threshold` — to distinguish operational from configuration objects. This produces inaccurate results: high-velocity integration-maintained objects get marked operational when they're clearly configuration, and slow-growth user-facing objects get marked configuration when they're not. The "empty" classification is redundant with "deprecated" and there's no signal for objects that were once active but are now dead.

## Taxonomy

Three classifications (down from four):

| Classification | Meaning |
|---|---|
| `operational` | Records created/modified by diverse end-users. Core business objects. |
| `configuration` | Records maintained by admins or system users. Setup/reference data. |
| `deprecated` | No records, or has records but zero recent activity. Dead weight. |

Manual override via `classification_source = "manual"` remains — the classifier never touches those.

## Classification Logic

Evaluated top-to-bottom, first match wins:

```
1. record_count == 0                                    → deprecated
2. velocity_score == 0  (has records, no recent mods)   → deprecated
3. creator_diversity query failed                       → configuration
4. creator_diversity_ratio <= threshold                 → configuration
5. creator_diversity_ratio > threshold                  → operational
```

### Creator Diversity

New SOQL query per object (only for objects with `record_count > 0` AND `velocity_score > 0`):

```sql
SELECT CreatedById, COUNT(Id) cnt
FROM {ObjectName}
GROUP BY CreatedById
```

Cross-reference each `CreatedById` against the User table. A creator is "admin/system" if ANY of:
- `Profile.Name` contains "System Administrator" or "Admin" (case-insensitive)
- `UserType` in (`AutomatedProcess`, `DefaultWorkflowUser`)
- `User.IsActive = false` AND `User.Name` matches common integration patterns (e.g. contains "Integration", "API", "Sync")

The admin user ID set is built once per sync from a single SOQL query and cached for all per-object creator queries.

Compute:

```
creator_diversity_ratio = unique_non_admin_creators / total_records
```

Default `creator_diversity_threshold`: **0.05** (configurable in Analysis Settings).

If the `GROUP BY CreatedById` query fails (unsupported object, permission issue), default to `configuration`.

### Data Collected During Sync

New field on `UsageData`:
- `creator_counts: dict[str, dict]` — per-object mapping of `{ "total_creators": int, "non_admin_creators": int }`

New fields on `MetadataObject`:
- `creator_diversity_score: float` — the computed ratio, stored for display and re-analysis without re-querying

The admin user list is fetched once at the start of `pull_usage_data` (single SOQL query for admin User IDs), then reused across all per-object creator queries.

### Configurable Thresholds

All thresholds live in `Organization.analysis_config` and are editable on the Organization page under "Analysis Settings":

| Field | Default | Help Text |
|---|---|---|
| `velocity_window_days` | `30` | "How far back to look for record modifications when measuring object activity. Larger windows smooth out seasonal variation." |
| `classification_threshold` | `0.05` | "Minimum ratio of unique non-admin record creators to total records. Objects above this threshold are classified as operational; below it, configuration." |
| `min_records_for_vectorization` | `1` | "Objects with fewer records than this value will not be included in AI vectorization." |

**Simplification:** `classification_threshold` is repurposed to mean the creator diversity threshold. Its default changes from `0.1` to `0.05`. No new column or config key needed — the meaning just changes. Any org with a custom value keeps it; the help text explains the new semantics.

### Frontend Help Text

The `AnalysisField` component gains an optional `helpText` prop rendered as a `<p>` below the label, styled `text-xs text-slate-500`. Each settings field gets the help text from the table above.

## Sync Progress Improvements

Two changes to make the sync feel more responsive:

### 1. Spinning indicator on platform card

The Sync button on the Analysis page currently stops spinning after the HTTP 202 returns. Fix: keep the button in its spinning state while `connection.status === 'syncing'`, not just while `syncConnection.isPending`.

### 2. Incremental object count during "Data Objects" phase

Currently the "Data Objects" phase chip shows "pulling" then jumps to "done 133". Change: call the `progress_callback` every 5 objects (or every 3 seconds, whichever comes first) during `pull_usage_data` with the current count. The frontend already polls every 2s so intermediate counts will appear naturally as "23 of 133", "48 of 133", etc.

The `PhaseChip` component updates to show `{count} of {total}` when status is `pulling` and `count > 0`. The total is not currently available in the phase data — add an optional `total` field to the phase info so the chip can display fractional progress.

## Migration

- Add `creator_diversity_score: Float` column to `metadata_objects` (nullable, default null). Alembic migration.
- Change `classification_threshold` default from `0.1` to `0.05` in `DEFAULT_CONFIG`.
- Remove `"empty"` from `ClassificationUpdate` schema's allowed values, add it as a legacy alias for `"deprecated"` if needed.
- Update `AnalysisField` component to accept `helpText` prop.
- No data migration needed — next sync populates `creator_diversity_score`, next classification run uses the new logic. Old objects without the score get classified on velocity alone until re-synced.

## What This Does NOT Include

- LLM-based classification (deferred — heuristics should cover 90%+ of cases)
- Cross-platform classification signals (future: HubSpot, etc.)
- Historical classification tracking or audit log
