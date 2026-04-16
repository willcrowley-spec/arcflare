# Sync Progress Indicators — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show real-time progress when a Salesforce metadata sync is running, fix the premature `last_sync_at` bug, and detect in-flight syncs on page load.

**Architecture:** Celery worker writes phase progress to a Redis hash during sync. A new API endpoint reads the hash. Frontend polls every 2s and renders a grid of metadata-type chips that transition independently (waiting → pulling → done).

**Tech Stack:** Redis (already deployed), FastAPI, React Query polling, Tailwind CSS

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/app/services/sync_progress.py` | Redis hash read/write for sync progress |
| Modify | `backend/app/services/salesforce/metadata.py` | Emit progress updates at each pull phase |
| Modify | `backend/app/workers/metadata_sync.py` | Init/complete progress, pass Redis client, update vectorization phase |
| Modify | `backend/app/api/routes/connections.py` | Fix `last_sync_at` bug, add `GET /{id}/sync-status`, set status to `syncing` |
| Modify | `frontend/src/api/client.ts` | Add `connections.syncStatus(id)` method |
| Modify | `frontend/src/hooks/useApi.ts` | Add `useSyncProgress` polling hook |
| Create | `frontend/src/components/SyncProgressPanel.tsx` | Phase chip grid UI component |
| Modify | `frontend/src/pages/Analysis/index.tsx` | Integrate progress panel into connection cards |

---

### Task 1: Backend — Sync Progress Redis Utility

**Files:**
- Create: `backend/app/services/sync_progress.py`

- [ ] **Step 1: Create the sync progress module**

```python
"""Sync progress tracking via Redis hashes."""
import logging
from datetime import UTC, datetime
from typing import Any

import redis

logger = logging.getLogger(__name__)

PHASES = [
    "objects",
    "fields",
    "flows",
    "triggers",
    "validation_rules",
    "apex_classes",
    "permissions",
    "ui_components",
    "reports",
    "installed_packages",
    "licensing",
    "user_velocity",
    "vectorization",
]

_KEY_PREFIX = "sync_progress"


def _key(connection_id: str) -> str:
    return f"{_KEY_PREFIX}:{connection_id}"


def get_redis_client() -> redis.Redis:
    from app.core.config import get_settings
    return redis.from_url(get_settings().REDIS_URL, decode_responses=True)


def init_progress(connection_id: str, r: redis.Redis | None = None) -> None:
    r = r or get_redis_client()
    k = _key(connection_id)
    mapping: dict[str, str] = {
        "status": "running",
        "started_at": datetime.now(tz=UTC).isoformat(),
        "completed_at": "",
        "error": "",
    }
    for phase in PHASES:
        mapping[phase] = "waiting:0"
    r.hset(k, mapping=mapping)
    r.expire(k, 3600)


def update_phase(
    connection_id: str,
    phase: str,
    status: str,
    count: int = 0,
    r: redis.Redis | None = None,
) -> None:
    r = r or get_redis_client()
    r.hset(_key(connection_id), phase, f"{status}:{count}")


def complete_progress(
    connection_id: str,
    error: str | None = None,
    r: redis.Redis | None = None,
) -> None:
    r = r or get_redis_client()
    k = _key(connection_id)
    r.hset(k, mapping={
        "status": "failed" if error else "completed",
        "completed_at": datetime.now(tz=UTC).isoformat(),
        "error": error or "",
    })
    r.expire(k, 300)


def get_progress(connection_id: str, r: redis.Redis | None = None) -> dict[str, Any]:
    r = r or get_redis_client()
    raw = r.hgetall(_key(connection_id))
    if not raw:
        return {"status": "idle"}
    phases: dict[str, dict[str, Any]] = {}
    for phase in PHASES:
        val = raw.get(phase, "waiting:0")
        parts = val.split(":", 1)
        phases[phase] = {
            "status": parts[0],
            "count": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
        }
    return {
        "status": raw.get("status", "idle"),
        "started_at": raw.get("started_at") or None,
        "completed_at": raw.get("completed_at") or None,
        "error": raw.get("error") or None,
        "phases": phases,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/sync_progress.py
git commit -m "feat: add sync progress Redis utility"
```

---

### Task 2: Backend — Inject Progress Updates into Metadata Sync

**Files:**
- Modify: `backend/app/services/salesforce/metadata.py:573-779`

The `sync_metadata` function needs progress updates injected at each phase boundary. The function signature gains an optional `progress_callback` parameter to avoid a hard Redis dependency in the service layer.

- [ ] **Step 1: Add progress_callback parameter to sync_metadata**

In `backend/app/services/salesforce/metadata.py`, change the function signature at line 573:

```python
async def sync_metadata(
    connection_id: UUID,
    db: AsyncSession,
    progress_callback: callable | None = None,
) -> int:
```

Add a helper inside the function body (right after the signature docstring):

```python
    def _progress(phase: str, status: str, count: int = 0) -> None:
        if progress_callback:
            try:
                progress_callback(str(connection_id), phase, status, count)
            except Exception:
                pass
```

- [ ] **Step 2: Add progress calls at each phase boundary**

After `objects = pull_object_describes(sf)` (line ~590), add:

```python
    _progress("objects", "done", len(objects))
```

After the usage loop that sets record counts (after line ~596), before automations:

```python
    _progress("fields", "pulling", sum(o.field_count for o in objects))
```

Before `automations = pull_all_automations(sf)`:

```python
    _progress("flows", "pulling", 0)
    _progress("triggers", "pulling", 0)
    _progress("validation_rules", "pulling", 0)
```

After `automations = pull_all_automations(sf)`:

```python
    flow_count = sum(1 for a in automations if a.automation_type in ("flow", "process_builder"))
    trigger_count = sum(1 for a in automations if a.automation_type == "trigger")
    vr_count = sum(1 for a in automations if a.automation_type == "validation_rule")
    _progress("flows", "done", flow_count)
    _progress("triggers", "done", trigger_count)
    _progress("validation_rules", "done", vr_count)
```

Before `permissions = pull_all_permissions(sf)`:

```python
    _progress("permissions", "pulling", 0)
```

After `permissions = pull_all_permissions(sf)`:

```python
    _progress("permissions", "done", len(permissions))
```

Before `ui_components = pull_all_ui_components(sf, object_names)`:

```python
    _progress("ui_components", "pulling", 0)
    _progress("reports", "pulling", 0)
```

After `ui_components = pull_all_ui_components(sf, object_names)`:

```python
    report_count = sum(1 for c in ui_components if c.component_type in ("report", "dashboard"))
    _progress("ui_components", "done", len(ui_components) - report_count)
    _progress("reports", "done", report_count)
```

After the DB persist loop, before `apex_classes = pull_apex_classes(sf)`:

```python
    _progress("fields", "done", sum(o.field_count for o in objects))
    _progress("apex_classes", "pulling", 0)
```

After `apex_classes = pull_apex_classes(sf)` and its DB persist loop:

```python
    _progress("apex_classes", "done", len(apex_classes))
```

Before `packages = pull_installed_packages(sf)`:

```python
    _progress("installed_packages", "pulling", 0)
```

After packages persist loop:

```python
    _progress("installed_packages", "done", len(packages))
```

Before `snapshot_licensing`:

```python
    _progress("licensing", "pulling", 0)
```

After `snapshot_licensing` try/except:

```python
    _progress("licensing", "done", 1)
```

Before `snapshot_user_velocity`:

```python
    _progress("user_velocity", "pulling", 0)
```

After `snapshot_user_velocity` try/except:

```python
    _progress("user_velocity", "done", 1)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/salesforce/metadata.py
git commit -m "feat: inject progress callbacks into sync_metadata phases"
```

---

### Task 3: Backend — Wire Progress into Celery Tasks

**Files:**
- Modify: `backend/app/workers/metadata_sync.py`

- [ ] **Step 1: Update sync_metadata_task to init/complete progress and pass callback**

Replace the entire file content with:

```python
from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.connection import PlatformConnection
    from app.services.salesforce.metadata import sync_metadata
    from app.services.sync_progress import (
        complete_progress,
        get_redis_client,
        init_progress,
        update_phase,
    )

    r = get_redis_client()
    init_progress(connection_id, r)

    def progress_cb(conn_id: str, phase: str, status: str, count: int = 0) -> None:
        update_phase(conn_id, phase, status, count, r)

    async def _run() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn:
                conn.status = "syncing"
                await session.commit()
            return await sync_metadata(UUID(connection_id), session, progress_callback=progress_cb)

    try:
        asyncio.run(_run())
        complete_progress(connection_id, r=r)
    except Exception as exc:
        complete_progress(connection_id, error=str(exc), r=r)
        raise

    async def _mark_connected() -> None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn:
                conn.status = "connected"
                await session.commit()

    asyncio.run(_mark_connected())

    vectorize_metadata_task.delay(connection_id)
    return connection_id


@celery_app.task(name="metadata.vectorize_metadata")
def vectorize_metadata_task(connection_id: str) -> str:
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.connection import PlatformConnection
    from app.services.metadata_vectorizer import vectorize_org_metadata
    from app.services.sync_progress import (
        complete_progress,
        get_redis_client,
        update_phase,
    )

    r = get_redis_client()
    update_phase(connection_id, "vectorization", "pulling", 0, r)

    async def _run() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn is None:
                return 0
            return await vectorize_org_metadata(UUID(connection_id), conn.org_id, session)

    try:
        count = asyncio.run(_run())
        update_phase(connection_id, "vectorization", "done", count, r)
    except Exception:
        update_phase(connection_id, "vectorization", "done", 0, r)

    return connection_id
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/workers/metadata_sync.py
git commit -m "feat: wire sync progress into Celery tasks with init/complete lifecycle"
```

---

### Task 4: Backend — Fix last_sync_at Bug + Add Sync Status Endpoint

**Files:**
- Modify: `backend/app/api/routes/connections.py:62-78` (fix bug)
- Modify: `backend/app/api/routes/connections.py` (add endpoint)

- [ ] **Step 1: Fix premature last_sync_at**

In `backend/app/api/routes/connections.py`, line 69, change:

```python
        last_sync_at=datetime.now(tz=UTC),
```

to:

```python
        last_sync_at=None,
```

- [ ] **Step 2: Add GET sync-status endpoint**

Add this endpoint after the existing `sync_connection` endpoint (after line 106):

```python
@router.get("/{connection_id}/sync-status")
async def get_sync_status(
    connection_id: UUID,
    org: CurrentOrg,
    db: DbSession,
) -> dict:
    """Return live sync progress from Redis."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    from app.services.sync_progress import get_progress
    return get_progress(str(connection_id))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes/connections.py
git commit -m "fix: last_sync_at null on creation, add sync-status polling endpoint"
```

---

### Task 5: Frontend — API Client + Polling Hook

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Add syncStatus method to API client**

In `frontend/src/api/client.ts`, inside the `connections` object (after the `delete` method on line 105), add:

```typescript
    syncStatus: (id: string) =>
      request<{
        status: string
        started_at: string | null
        completed_at: string | null
        error: string | null
        phases?: Record<string, { status: string; count: number }>
      }>(`/connections/${id}/sync-status`),
```

- [ ] **Step 2: Add useSyncProgress hook**

In `frontend/src/hooks/useApi.ts`, add this hook at the end of the file:

```typescript
export function useSyncProgress(connectionId: string | null) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['sync-progress', connectionId],
    queryFn: () => api.connections.syncStatus(connectionId!),
    enabled: !!connectionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed' || status === 'idle') return false
      return 2000
    },
  })

  const isDone = query.data?.status === 'completed'
  const isFailed = query.data?.status === 'failed'

  if (isDone || isFailed) {
    void qc.invalidateQueries({ queryKey: ['connections'] })
    void qc.invalidateQueries({ queryKey: ['metadata'] })
    void qc.invalidateQueries({ queryKey: ['organization'] })
  }

  return query
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat: add syncStatus API method and useSyncProgress polling hook"
```

---

### Task 6: Frontend — SyncProgressPanel Component

**Files:**
- Create: `frontend/src/components/SyncProgressPanel.tsx`

- [ ] **Step 1: Create the progress panel component**

```tsx
import { useEffect, useRef, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface PhaseInfo {
  status: string
  count: number
}

interface SyncProgressData {
  status: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  phases?: Record<string, PhaseInfo>
}

const PHASE_LABELS: Record<string, string> = {
  objects: 'Objects',
  fields: 'Fields',
  flows: 'Flows',
  triggers: 'Triggers',
  validation_rules: 'Validation Rules',
  apex_classes: 'Apex Classes',
  permissions: 'Permissions',
  ui_components: 'UI Components',
  reports: 'Reports & Dashboards',
  installed_packages: 'Packages',
  licensing: 'Licensing',
  user_velocity: 'User Velocity',
  vectorization: 'Vectorization',
}

const PHASE_ORDER = Object.keys(PHASE_LABELS)

function PhaseChip({ name, info }: { name: string; info: PhaseInfo }) {
  const label = PHASE_LABELS[name] ?? name
  const isWaiting = info.status === 'waiting'
  const isPulling = info.status === 'pulling'
  const isDone = info.status === 'done'

  return (
    <div
      className={clsx(
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-all duration-300',
        isWaiting && 'border-slate-200 bg-slate-50 text-slate-400',
        isPulling && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        isDone && 'border-emerald-200 bg-emerald-50 text-emerald-800',
      )}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
        {isWaiting && <span className="h-2 w-2 rounded-full bg-slate-300" />}
        {isPulling && <Loader2 className="h-4 w-4 animate-spin text-sky-600" />}
        {isDone && <Check className="h-4 w-4 text-emerald-600" />}
      </span>
      <span className="font-medium">{label}</span>
      {isDone && info.count > 0 && (
        <span className="ml-auto tabular-nums text-xs font-semibold">{info.count.toLocaleString()}</span>
      )}
    </div>
  )
}

export function SyncProgressPanel({
  data,
  onDismiss,
}: {
  data: SyncProgressData | undefined
  onDismiss?: () => void
}) {
  const [dismissed, setDismissed] = useState(false)
  const completedAtRef = useRef<number | null>(null)

  const isRunning = data?.status === 'running'
  const isCompleted = data?.status === 'completed'
  const isFailed = data?.status === 'failed'

  useEffect(() => {
    if (isCompleted && !completedAtRef.current) {
      completedAtRef.current = Date.now()
      const timer = setTimeout(() => {
        setDismissed(true)
        onDismiss?.()
      }, 4000)
      return () => clearTimeout(timer)
    }
    if (isRunning) {
      completedAtRef.current = null
      setDismissed(false)
    }
  }, [isCompleted, isRunning, onDismiss])

  if (!data || data.status === 'idle' || dismissed) return null

  const phases = data.phases ?? {}
  const doneCount = PHASE_ORDER.filter((p) => phases[p]?.status === 'done').length
  const totalPhases = PHASE_ORDER.length

  return (
    <div
      className={clsx(
        'rounded-xl border p-5 transition-all duration-500',
        isRunning && 'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        isCompleted && 'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        isFailed && 'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {isRunning && 'Syncing metadata…'}
            {isCompleted && 'Sync complete'}
            {isFailed && 'Sync failed'}
          </p>
          <p className="text-xs text-slate-500">
            {isRunning && `${doneCount} of ${totalPhases} phases complete`}
            {isCompleted && `All ${totalPhases} phases complete`}
            {isFailed && (data.error || 'An error occurred during sync')}
          </p>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-sky-500 transition-all duration-500"
                style={{ width: `${(doneCount / totalPhases) * 100}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-slate-500">
              {Math.round((doneCount / totalPhases) * 100)}%
            </span>
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {PHASE_ORDER.map((phase) => (
          <PhaseChip
            key={phase}
            name={phase}
            info={phases[phase] ?? { status: 'waiting', count: 0 }}
          />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SyncProgressPanel.tsx
git commit -m "feat: create SyncProgressPanel component with phase chip grid"
```

---

### Task 7: Frontend — Integrate Progress Panel into Analysis Page

**Files:**
- Modify: `frontend/src/pages/Analysis/index.tsx`

- [ ] **Step 1: Add imports**

At the top of `frontend/src/pages/Analysis/index.tsx`, add to existing imports:

```typescript
import { SyncProgressPanel } from '@/components/SyncProgressPanel'
import { useSyncProgress } from '@/hooks/useApi'
```

- [ ] **Step 2: Add sync progress state and hook**

Inside `AnalysisPage()`, after the existing `syncingId` state (line 208), add:

```typescript
  const [activeSyncId, setActiveSyncId] = useState<string | null>(null)
  const syncProgressQuery = useSyncProgress(activeSyncId)
```

- [ ] **Step 3: Auto-detect running sync on page load**

After the `connections` variable is set (line 215), add:

```typescript
  useEffect(() => {
    if (!activeSyncId && connections.length > 0) {
      const syncing = connections.find((c) => String(c.status).toLowerCase() === 'syncing')
      if (syncing) {
        setActiveSyncId(String(syncing.id))
      }
    }
  }, [connections, activeSyncId])
```

Add `useEffect` to the imports from `react` at line 1 if not already there.

- [ ] **Step 4: Update onSync to activate progress tracking**

Replace the existing `onSync` callback (lines 339-347) with:

```typescript
  const onSync = useCallback(
    (id: string) => {
      setSyncingId(id)
      setActiveSyncId(id)
      syncConnection.mutate(id, {
        onSettled: () => setSyncingId(null),
      })
    },
    [syncConnection],
  )
```

- [ ] **Step 5: Render the progress panel above the connection cards**

Inside the Platform Sources `<section>` (around line 1013 where the connection grid starts), add the progress panel just before the `<div className="mt-6 grid gap-4 ...">`:

```tsx
        {activeSyncId && (
          <div className="mt-6">
            <SyncProgressPanel
              data={syncProgressQuery.data}
              onDismiss={() => setActiveSyncId(null)}
            />
          </div>
        )}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Analysis/index.tsx
git commit -m "feat: integrate sync progress panel into Analysis page with auto-detect"
```

---

### Task 8: Deploy and Verify

- [ ] **Step 1: Push all commits**

```bash
git push origin master
```

- [ ] **Step 2: Verify end-to-end**

1. Open `https://arcflare-frontend-production.up.railway.app`
2. Log in, navigate to Analysis
3. If already connected, click **Sync** — progress panel should appear with chips transitioning
4. Verify "Last sync" shows `—` on a fresh connection (not "Just now")
5. Verify progress panel auto-detects running sync on page refresh
6. Verify panel auto-dismisses after completion and data tables refresh
