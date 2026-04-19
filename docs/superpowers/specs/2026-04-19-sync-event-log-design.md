# Sync Event Log — Design Spec

**Date:** 2026-04-19
**Status:** Approved
**Goal:** Replace opaque sync progress pills with a rich, real-time sync event log that streams structured events to the UI and persists them for audit/debugging.

---

## Problem

The current sync UI shows grey pills that flip to green when a phase completes. Between updates there's no indication of what's happening, how long it's been, or whether things are progressing. The underlying progress system (Redis hash polled every 2s) only tracks phase-level status with no detail. When syncs fail, there's no log to inspect — just "error."

## Design Principles

1. **No silent fallbacks** — every operation emits an event. If something fails, the log says what and why.
2. **Two granularity levels** — phase events (always visible) and item events (collapsible detail).
3. **SSE over polling** — events appear instantly, no 2-second lag.
4. **Postgres for persistence** — queryable, auditable, tenant-scoped. Last 3 runs per connection.
5. **Redis pub/sub for real-time** — worker publishes, SSE endpoint subscribes. Ephemeral.

---

## Data Model

### Table: `sync_events`

```sql
CREATE TABLE sync_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id   UUID NOT NULL REFERENCES platform_connections(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL,  -- groups events per sync invocation
    sequence        INTEGER NOT NULL,  -- monotonic ordering within a run
    event_type      VARCHAR(30) NOT NULL,  -- run_start, phase_start, phase_complete, item, error, warning, run_complete
    phase           VARCHAR(50),  -- mdapi_retrieve, automations, etc. NULL for run-level events
    message         TEXT NOT NULL,  -- human-readable: "Parsed Account.object-meta.xml — 3 validation rules"
    detail_json     JSONB NOT NULL DEFAULT '{}',  -- structured payload (counts, durations, file paths, error traces)
    severity        VARCHAR(10) NOT NULL DEFAULT 'info',  -- info, warning, error
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_sync_events_connection_run ON sync_events (connection_id, run_id, sequence);
CREATE INDEX ix_sync_events_run_id ON sync_events (run_id);
```

### Event Types

| event_type | phase | When emitted | Example message |
|---|---|---|---|
| `run_start` | NULL | Sync task begins | "Metadata sync started" |
| `phase_start` | set | Phase begins | "Retrieving metadata via MDAPI..." |
| `phase_complete` | set | Phase finishes | "MDAPI retrieve complete — 47 files" |
| `item` | set | Individual item processed | "Parsed Account.object-meta.xml — 5 fields, 3 validation rules" |
| `warning` | set or NULL | Non-fatal issue | "FlowDefinitionView not available — skipping flow version check" |
| `error` | set or NULL | Fatal or caught error | "MDAPI retrieve failed: INSUFFICIENT_ACCESS" |
| `run_complete` | NULL | Sync task ends | "Sync complete — 133 objects, 42 automations, 15 components" |

### Detail JSON Examples

```json
// phase_complete for mdapi_retrieve
{
  "file_count": 47,
  "duration_ms": 14230,
  "types": {"Flow": 12, "ApexClass": 18, "CustomObject": 8, "ApexTrigger": 3, "Workflow": 4, "ApprovalProcess": 2}
}

// item for Apex parsing
{
  "api_name": "AccountService",
  "component_type": "apex_class",
  "dml_objects": ["Account", "Contact"],
  "soql_objects": ["Contact"],
  "method_count": 3,
  "skipped": false
}

// run_complete
{
  "duration_ms": 87340,
  "objects": 133,
  "automations": 42,
  "components": 15,
  "dependencies": 89,
  "communities": 4,
  "errors": 0,
  "warnings": 1
}
```

---

## Retention

On each sync start, before emitting `run_start`, purge old runs:

```sql
DELETE FROM sync_events
WHERE connection_id = :cid
AND run_id NOT IN (
    SELECT run_id FROM (
        SELECT run_id, MAX(created_at) AS latest
        FROM sync_events
        WHERE connection_id = :cid
        GROUP BY run_id
        ORDER BY latest DESC
        LIMIT 2  -- keep 2 previous runs; current run hasn't been inserted yet
    ) AS recent
);
```

This happens inside the worker before the first event is emitted, so the current run doesn't exist yet — we keep the 2 most recent previous runs, giving 3 total once the current run starts.

---

## Backend Architecture

### 1. Event Emitter (`app/services/sync_event_log.py`)

```python
class SyncEventEmitter:
    """Emits structured sync events to Postgres + Redis pub/sub."""

    def __init__(self, connection_id: UUID, org_id: UUID, run_id: UUID, db: AsyncSession):
        self.connection_id = connection_id
        self.org_id = org_id
        self.run_id = run_id
        self.db = db
        self._sequence = 0
        self._redis = get_redis_client()
        self._channel = f"sync_events:{connection_id}"

    async def emit(self, event_type: str, message: str, *,
                   phase: str | None = None,
                   detail: dict | None = None,
                   severity: str = "info") -> None:
        self._sequence += 1
        event = SyncEvent(
            connection_id=self.connection_id,
            org_id=self.org_id,
            run_id=self.run_id,
            sequence=self._sequence,
            event_type=event_type,
            phase=phase,
            message=message,
            detail_json=detail or {},
            severity=severity,
        )
        self.db.add(event)
        await self.db.flush()

        # Publish to Redis for SSE subscribers
        payload = {
            "sequence": self._sequence,
            "event_type": event_type,
            "phase": phase,
            "message": message,
            "detail": detail or {},
            "severity": severity,
            "created_at": event.created_at.isoformat(),
        }
        self._redis.publish(self._channel, json.dumps(payload))
```

### 2. SSE Endpoint (`app/api/routes/connections.py`)

```
GET /connections/{connection_id}/sync-stream
Accept: text/event-stream
```

Behavior:
1. Query Postgres for all events in the latest `run_id` — yield as SSE `event: backfill` messages.
2. Subscribe to Redis channel `sync_events:{connection_id}`.
3. Yield new events as `event: sync_event` messages.
4. On `run_complete` event, yield `event: done` and close.
5. Send keepalive comments (`: keepalive\n\n`) every 15 seconds to prevent proxy timeouts.
6. Handle client disconnect (stop Redis subscription, clean up).

### 3. Worker Integration (`app/workers/metadata_sync.py`)

Replace the current `progress_cb` pattern. Instead of `_progress(phase, status, count)`, the worker creates a `SyncEventEmitter` and passes it through the pipeline:

```python
emitter = SyncEventEmitter(connection_id, org_id, run_id, session)
await emitter.emit("run_start", "Metadata sync started")

# Inside sync_metadata, emit phase and item events
await emitter.emit("phase_start", "Retrieving metadata via MDAPI...", phase="mdapi_retrieve")
# ... work happens, individual items emit "item" events ...
await emitter.emit("phase_complete", f"MDAPI retrieve complete — {len(files)} files",
                    phase="mdapi_retrieve", detail={"file_count": len(files), ...})
```

### 4. Backward Compatibility

- Keep the existing Redis hash progress system (`sync_progress.py`) running in parallel during transition — the current `SyncProgressPanel` still reads from it.
- The new `SyncEventLogPanel` reads from the SSE stream.
- Once the new UI is stable, remove the old polling/Redis hash system.

---

## Frontend Architecture

### SSE Hook: `useSyncEventStream`

```typescript
function useSyncEventStream(connectionId: string | null) {
  const [events, setEvents] = useState<SyncEvent[]>([])
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle')

  useEffect(() => {
    if (!connectionId) return
    const es = new EventSource(`/api/v1/connections/${connectionId}/sync-stream`)

    es.addEventListener('backfill', (e) => {
      setEvents(JSON.parse(e.data))
      setStatus('running')
    })

    es.addEventListener('sync_event', (e) => {
      const event = JSON.parse(e.data)
      setEvents(prev => [...prev, event])
      if (event.event_type === 'run_complete') setStatus('completed')
      if (event.severity === 'error' && event.event_type === 'error') setStatus('failed')
    })

    es.addEventListener('done', () => es.close())
    es.onerror = () => { setStatus('failed'); es.close() }

    return () => es.close()
  }, [connectionId])

  return { events, status }
}
```

### Component: `SyncEventLogPanel`

**Layout (top to bottom):**

```
┌─────────────────────────────────────────────────────┐
│  Syncing metadata...          ●━━━━━━━━━━━━━ 45%    │
│  4 of 11 phases complete           Elapsed: 1m 23s  │
├─────────────────────────────────────────────────────┤
│ ✓ Data Objects    133  │ ● Automations        │ ... │
│ ✓ MDAPI Retrieve   47  │   Code Assets        │     │
│ ✓ MDAPI Parse      67  │   Security           │     │
├─────────────────────────────────────────────────────┤
│ ▼ Sync Log                                    ≡ ──  │
│                                                     │
│  22:11:12  Metadata sync started                    │
│  22:11:39  ━━ Data Objects ━━━━━━━━━━━━━━━━━━━━━━  │
│  22:11:39  Pulled 133 object describes              │
│  22:12:03  ━━ Usage Data ━━━━━━━━━━━━━━━━━━━━━━━━  │
│  22:12:03  Usage complete — 74 with records         │
│  22:12:03  ━━ MDAPI Retrieve ━━━━━━━━━━━━━━━━━━━━  │
│  22:14:18  Retrieved 47 files (14.2s)               │
│  22:14:18  ━━ MDAPI Parse ━━━━━━━━━━━━━━━━━━━━━━━  │
│  22:14:18    ▸ Parsed Account.object-meta.xml       │
│  22:14:18      5 fields, 3 validation rules         │
│  22:14:18    ▸ Parsed AccountService.cls            │
│  22:14:18      3 methods, DML: Account, Contact     │
│  22:14:19    ▸ Skipped ManagedPkg__c.cls (hidden)   │
│  22:14:19  Parse complete — 67 components           │
│  22:14:19  ━━ Automations ━━━━━━━━━━━━━━━━━━━━━━━  │
│  ●                                                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Behavior:**
- Terminal panel uses monospace font, dark background (`gray-900`), light text
- Phase headers rendered as bold divider lines with timestamps
- Item events indented and in subdued text (`gray-400`)
- Errors in `red-400`, warnings in `amber-400`
- Auto-scrolls to bottom; pauses when user scrolls up; "Jump to bottom" button appears
- Panel starts collapsed, auto-expands when sync starts
- After sync, panel stays open showing the final log

**Sync History dropdown:**
- Small dropdown above the log panel: "Run 1 (now) | Run 2 (Apr 17) | Run 3 (Apr 15)"
- Selecting a previous run loads its events from Postgres via `GET /connections/{id}/sync-events?run_id={uuid}`

### Phase Pills Update

The existing `SyncProgressPanel` phase pills are updated:
- Show ALL 16 backend phases (add `mdapi_retrieve`, `mdapi_parse`, `graph_build` — currently hidden)
- Map to friendlier labels (e.g., `mdapi_retrieve` → "Metadata Retrieve", `graph_build` → "Dependency Graph")
- Each pill derives its state from the event stream (not the Redis hash)
- Spinner animation while `phase_start` received but no `phase_complete`
- Count shown next to completed phases

---

## API Endpoints

### New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/connections/{id}/sync-stream` | SSE stream of live + backfilled events |
| GET | `/connections/{id}/sync-events` | JSON list of events for a run (`?run_id=` optional, defaults to latest) |
| GET | `/connections/{id}/sync-runs` | JSON list of last 3 run summaries (run_id, started_at, completed_at, status, event_count) |

### Existing Endpoints (kept during transition)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/connections/{id}/sync-status` | Current Redis hash progress (deprecated once new UI ships) |
| POST | `/connections/{id}/sync` | Trigger sync (unchanged) |

---

## Migration Path

1. **Phase 1**: Add `sync_events` table + `SyncEventEmitter` + emit events alongside existing progress callbacks. Add SSE endpoint. No frontend changes yet.
2. **Phase 2**: Build `SyncEventLogPanel` component. Wire to SSE. Run alongside old `SyncProgressPanel`.
3. **Phase 3**: Replace `SyncProgressPanel` with the new component. Remove old Redis hash polling from frontend.
4. **Phase 4**: Remove `sync_progress.py` Redis hash system from backend. Clean up.

---

## Out of Scope

- **Operator observability** (Axiom/BetterStack) — separate effort, deferred.
- **Push notifications** (email/Slack on sync complete/fail) — future enhancement.
- **Per-object progress bars** (Airbyte-style "47/133 objects") — the item-level events give equivalent visibility without needing pre-counted totals.
- **Diff between sync runs** ("what changed since last sync") — valuable but separate feature.

---

## Dependencies

- Redis pub/sub (already available via the Redis instance used for Celery broker)
- SSE infrastructure (pattern exists in `chat.py` with `StreamingResponse`)
- Alembic migration for `sync_events` table
- No new external services
