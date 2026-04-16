# Sync Progress Indicators — Design Spec

**Date:** 2026-04-15
**Status:** Draft

## Problem

1. Connecting a Salesforce org fires an auto-sync, but there's zero visual feedback — the user lands on the Analysis page with no indication that work is happening.
2. `last_sync_at` is set to `now()` when the connection row is *created*, before any sync runs. This makes "Last sync: Just now" appear immediately, which is misleading.
3. Clicking the Sync button enqueues a Celery task and returns instantly. The UI briefly spins the icon then stops. No progress, no phase info, no counts.

## Goals

- Show real-time-ish progress when a sync is running — whether triggered by auto-sync on connect or by the Sync button.
- Display a grid of metadata type indicators that transition independently: `waiting → pulling → done (count)`.
- Fix the premature `last_sync_at` timestamp.
- Make the experience feel parallel and fast, matching enterprise benchmarks (Gearset, Ownbackup, etc.).

## Non-Goals

- Removing auto-sync on connect (kept, but now visible).
- Full log streaming or deployment-console-style output.
- WebSocket or SSE transport (polling is sufficient).

---

## Architecture

### Transport: Redis hash + polling

**Why:** We already have Redis for Celery. A Redis hash per sync gives O(1) reads, auto-expires, and requires no schema changes.

**Key format:** `sync_progress:{connection_id}`

**Hash fields:**

| Field | Example value | Description |
|-------|--------------|-------------|
| `status` | `running` / `completed` / `failed` | Overall sync status |
| `started_at` | ISO 8601 | When sync began |
| `completed_at` | ISO 8601 or empty | When sync finished |
| `error` | string or empty | Error message if failed |
| `objects` | `done:247` | Phase status and count |
| `fields` | `pulling:832` | In-progress with running count |
| `flows` | `waiting:0` | Not started yet |
| `triggers` | `done:12` | Completed |
| `validation_rules` | `waiting:0` | |
| `apex_classes` | `waiting:0` | |
| `permissions` | `waiting:0` | |
| `ui_components` | `waiting:0` | |
| `reports` | `waiting:0` | |
| `installed_packages` | `waiting:0` | |
| `licensing` | `waiting:0` | |
| `user_velocity` | `waiting:0` | |
| `vectorization` | `waiting:0` | |

Each metadata-type field uses the format `status:count` where status is `waiting`, `pulling`, or `done`.

**TTL:** 300 seconds (5 minutes) after sync completes, auto-cleaned.

### Backend changes

#### 1. Progress writer utility

New module: `backend/app/services/sync_progress.py`

Provides:
- `init_progress(connection_id, redis)` — creates the hash with all types set to `waiting:0`, status=`running`, TTL 1 hour.
- `update_phase(connection_id, phase_name, status, count, redis)` — updates a single field.
- `complete_progress(connection_id, redis, error=None)` — sets status to `completed` or `failed`, sets TTL to 300s.
- `get_progress(connection_id, redis)` — reads the full hash, returns a dict.

#### 2. Modify `sync_metadata` in `metadata.py`

Inject progress updates at each phase boundary. After each `pull_*` function returns, call `update_phase(conn_id, "objects", "done", len(objects), redis)` etc.

Before starting each pull: `update_phase(conn_id, "flows", "pulling", 0, redis)`.

#### 3. Modify `vectorize_metadata_task`

Update the `vectorization` phase from `waiting` → `pulling` → `done`.

#### 4. Fix `last_sync_at` bug

In `connections.py` OAuth callback (line 69): change `last_sync_at=datetime.now(tz=UTC)` to `last_sync_at=None`. The real timestamp gets set at the end of `sync_metadata` (line 765 of `metadata.py`), which is correct.

#### 5. New API endpoint

`GET /api/v1/connections/{connection_id}/sync-status`

Returns the Redis hash as JSON:

```json
{
  "status": "running",
  "started_at": "2026-04-15T18:30:00Z",
  "completed_at": null,
  "error": null,
  "phases": {
    "objects": { "status": "done", "count": 247 },
    "fields": { "status": "done", "count": 1832 },
    "flows": { "status": "pulling", "count": 22 },
    "triggers": { "status": "waiting", "count": 0 },
    "validation_rules": { "status": "waiting", "count": 0 },
    "apex_classes": { "status": "waiting", "count": 0 },
    "permissions": { "status": "waiting", "count": 0 },
    "ui_components": { "status": "waiting", "count": 0 },
    "reports": { "status": "waiting", "count": 0 },
    "installed_packages": { "status": "waiting", "count": 0 },
    "licensing": { "status": "waiting", "count": 0 },
    "user_velocity": { "status": "waiting", "count": 0 },
    "vectorization": { "status": "waiting", "count": 0 }
  }
}
```

When no hash exists in Redis (no sync running or expired), returns `{ "status": "idle" }`.

#### 6. Modify connection status

When sync starts: set `PlatformConnection.status = "syncing"`.
When sync ends: set `PlatformConnection.status = "connected"`.

This lets the frontend detect in-flight syncs on page load via the existing `GET /connections` response.

### Frontend changes

#### 1. New hook: `useSyncProgress(connectionId, enabled)`

- Polls `GET /connections/{id}/sync-status` every 2 seconds when `enabled` is true.
- Stops polling when status is `completed`, `failed`, or `idle`.
- On completion, invalidates the metadata queries (objects, automations, components, summary) so the tables refresh.

#### 2. Progress panel component: `SyncProgressPanel`

Renders inside the connection card when a sync is detected (either from button click or from `connection.status === "syncing"` on page load).

Layout: a 2-column grid of phase chips inside the connection card. Each chip shows:
- **Waiting:** muted style, dash for count
- **Pulling:** animated pulse/spinner, count updates live
- **Done:** checkmark, final count

When all phases are done, the panel shows a brief "Sync complete" confirmation with total counts, then collapses after 3 seconds. The connection card reverts to its normal state with an updated "Last sync" timestamp.

#### 3. Auto-detect running sync on page load

When the Analysis page loads and `connections` data arrives, check each connection's `status`. If any is `"syncing"`, activate `useSyncProgress` for that connection. This handles the OAuth-redirect-then-auto-sync scenario — user lands on the page and immediately sees progress.

#### 4. Sync button behavior

When clicked:
1. Call `POST /connections/{id}/sync` (existing).
2. Immediately activate `useSyncProgress` for that connection.
3. Disable the Sync button while running.

---

## Error handling

- If the Celery task crashes, `complete_progress` may not fire. The Redis hash TTL (1 hour for running) ensures it doesn't persist forever. The frontend treats "no response change for 2 minutes" as stale and shows a "Sync may have failed — try again" message.
- If individual phases fail (e.g., Tooling API rate limit on Apex), the worker logs the error, marks that phase as `done:0`, and continues to the next phase. The overall sync still completes.
- The `error` field on the progress hash captures fatal errors (auth expired, connection dropped).

## Testing plan

1. Connect a new org → verify progress panel appears automatically on redirect.
2. Click Sync on existing connection → verify panel expands with live phase transitions.
3. Verify `last_sync_at` is null on fresh connection, set only after sync completes.
4. Kill the worker mid-sync → verify frontend eventually shows stale/failed state.
5. Run two connections simultaneously → verify independent progress panels.
