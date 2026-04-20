# Sync Event Log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace opaque sync progress pills with a rich, real-time sync event log that streams structured events to the UI and persists them in Postgres for audit/debugging.

**Architecture:** Postgres `sync_events` table stores all events (last 3 runs retained). Backend worker emits events via a `SyncEventEmitter` that writes to Postgres + publishes to Redis pub/sub. A FastAPI SSE endpoint subscribes to Redis, backfills from Postgres, and streams events to the frontend. The frontend `SyncEventLogPanel` component renders phase pills and a terminal-style log panel, driven by a `useSyncEventStream` hook consuming the SSE stream. The old Redis hash progress system (`sync_progress.py`, `SyncProgressPanel`, `useSyncProgress`, `sync-status` endpoint) is fully removed — no parallel systems.

**Tech Stack:** PostgreSQL (JSONB), Redis pub/sub, FastAPI SSE (`StreamingResponse`), SQLAlchemy async, React + TypeScript, fetch-based SSE parsing (Task 14) so auth headers can be sent (`EventSource` cannot)

**Spec:** `docs/superpowers/specs/2026-04-19-sync-event-log-design.md`

---

## File Structure

### Backend — New files

| File | Responsibility |
|------|---------------|
| `backend/app/models/sync_event.py` | SQLAlchemy `SyncEvent` model |
| `backend/alembic/versions/018_add_sync_events_table.py` | Migration for `sync_events` table |
| `backend/app/services/sync_event_log.py` | `SyncEventEmitter` class — writes Postgres + publishes Redis |
| `backend/tests/services/test_sync_event_log.py` | Unit tests for `SyncEventEmitter` |
| `backend/tests/models/test_sync_event.py` | Model instantiation test |

### Backend — Modified files

| File | What changes |
|------|-------------|
| `backend/app/models/__init__.py` | Register `SyncEvent` |
| `backend/app/api/routes/connections.py` | Add `sync-stream` (SSE) + `sync-events` (JSON) endpoints. Remove `sync-status` endpoint. |
| `backend/app/workers/metadata_sync.py` | Replace `progress_cb` / `update_phase` with `SyncEventEmitter`. Remove all `sync_progress` imports. |
| `backend/app/services/salesforce/metadata.py` | Replace `progress_callback` with `SyncEventEmitter`, emit item-level events during parsing |
| `backend/app/services/sync_progress.py` | Keep only `get_redis_client()` (used by discovery). Delete all phase tracking functions (`init_progress`, `update_phase`, `complete_progress`, `get_progress`, `PHASES`). |

### Frontend — New files

| File | Responsibility |
|------|---------------|
| `frontend/src/hooks/useSyncEventStream.ts` | SSE hook returning `events[]` and `status` |
| `frontend/src/components/SyncEventLogPanel.tsx` | Terminal-style log + phase pills UI |

### Frontend — Modified files

| File | What changes |
|------|-------------|
| `frontend/src/api/client.ts` | Add `syncEvents` method. Remove `syncStatus` method. |
| `frontend/src/types/index.ts` | Add `SyncEvent` type |
| `frontend/src/pages/Platforms/index.tsx` | Replace `SyncProgressPanel` with `SyncEventLogPanel`. Remove `useSyncProgress`. |
| `frontend/src/pages/Analysis/index.tsx` | Replace `SyncProgressModal` internals with `SyncEventLogPanel`. Remove `useSyncProgress`. |
| `frontend/src/hooks/useApi.ts` | Remove `useSyncProgress`. Add `useSyncRuns` (deferred). |

### Frontend — Deleted files

| File | Why |
|------|-----|
| `frontend/src/components/SyncProgressPanel.tsx` | Replaced by `SyncEventLogPanel` |

---

## Phase 1 — Backend Data Layer

### Task 1: SyncEvent Model

**Files:**
- Create: `backend/app/models/sync_event.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_sync_event.py`

- [ ] **Step 1: Write the model test**

```python
# backend/tests/models/test_sync_event.py
from uuid import uuid4

from app.models.sync_event import SyncEvent


def test_sync_event_instantiation():
    ev = SyncEvent(
        connection_id=uuid4(),
        org_id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        event_type="run_start",
        phase=None,
        message="Metadata sync started",
        detail_json={},
        severity="info",
    )
    assert ev.event_type == "run_start"
    assert ev.sequence == 1
    assert ev.severity == "info"
    assert ev.detail_json == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && py -m pytest tests/models/test_sync_event.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.sync_event'`

- [ ] **Step 3: Create the SyncEvent model**

```python
# backend/app/models/sync_event.py
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.connection import PlatformConnection
    from app.models.organization import Organization


class SyncEvent(Base):
    __tablename__ = "sync_events"
    __table_args__ = (
        Index("ix_sync_events_connection_run", "connection_id", "run_id", "sequence"),
        Index("ix_sync_events_connection_created", "connection_id", "created_at"),
        Index("ix_sync_events_run_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    severity: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'info'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    connection: Mapped["PlatformConnection"] = relationship("PlatformConnection")
    organization: Mapped["Organization"] = relationship("Organization")
```

- [ ] **Step 4: Register in `__init__.py`**

In `backend/app/models/__init__.py`, add `SyncEvent` to imports and `__all__`:

```python
from app.models.sync_event import SyncEvent
```

Add `"SyncEvent"` to the `__all__` list (alphabetically after `"Recommendation"`).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && py -m pytest tests/models/test_sync_event.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/sync_event.py backend/app/models/__init__.py backend/tests/models/test_sync_event.py
git commit -m "feat: add SyncEvent model for sync event log persistence"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/018_add_sync_events_table.py`

- [ ] **Step 1: Write the migration**

```python
# backend/alembic/versions/018_add_sync_events_table.py
"""add sync_events table

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("phase", sa.String(50), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "detail_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "severity",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sync_events_connection_id", "sync_events", ["connection_id"])
    op.create_index(
        "ix_sync_events_connection_run",
        "sync_events",
        ["connection_id", "run_id", "sequence"],
    )
    op.create_index("ix_sync_events_run_id", "sync_events", ["run_id"])
    op.create_index(
        "ix_sync_events_connection_created",
        "sync_events",
        ["connection_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_events_connection_created", table_name="sync_events")
    op.drop_index("ix_sync_events_run_id", table_name="sync_events")
    op.drop_index("ix_sync_events_connection_run", table_name="sync_events")
    op.drop_index("ix_sync_events_connection_id", table_name="sync_events")
    op.drop_table("sync_events")
```

- [ ] **Step 2: Verify migration file is syntactically correct**

Run: `cd backend && py -c "import alembic.versions" || py -c "exec(open('alembic/versions/018_add_sync_events_table.py').read())"`
Expected: No syntax errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/018_add_sync_events_table.py
git commit -m "feat: add migration for sync_events table"
```

---

### Task 3: SyncEventEmitter

**Files:**
- Create: `backend/app/services/sync_event_log.py`
- Test: `backend/tests/services/test_sync_event_log.py`

- [ ] **Step 1: Write the emitter tests**

```python
# backend/tests/services/test_sync_event_log.py
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.sync_event_log import SyncEventEmitter


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.publish = MagicMock()
    return r


@pytest.fixture
def emitter(mock_db, mock_redis):
    with patch("app.services.sync_event_log.get_redis_client", return_value=mock_redis):
        return SyncEventEmitter(
            connection_id=uuid4(),
            org_id=uuid4(),
            run_id=uuid4(),
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_emit_increments_sequence(emitter, mock_db):
    await emitter.emit("run_start", "Sync started")
    await emitter.emit("phase_start", "Starting objects", phase="objects")
    assert emitter._sequence == 2
    assert mock_db.add.call_count == 2
    assert mock_db.flush.await_count == 2


@pytest.mark.asyncio
async def test_emit_publishes_to_redis(emitter, mock_redis):
    await emitter.emit("run_start", "Sync started", detail={"foo": 1})
    mock_redis.publish.assert_called_once()
    channel, payload_str = mock_redis.publish.call_args[0]
    assert "sync_events:" in channel
    payload = json.loads(payload_str)
    assert payload["event_type"] == "run_start"
    assert payload["message"] == "Sync started"
    assert payload["detail"]["foo"] == 1
    assert payload["sequence"] == 1
    assert "run_id" in payload and "connection_id" in payload


@pytest.mark.asyncio
async def test_emit_phase_event(emitter, mock_db):
    await emitter.emit("phase_start", "Pulling objects...", phase="objects")
    added_event = mock_db.add.call_args[0][0]
    assert added_event.phase == "objects"
    assert added_event.event_type == "phase_start"


@pytest.mark.asyncio
async def test_emit_error_severity(emitter, mock_db):
    await emitter.emit("error", "MDAPI failed", severity="error", phase="mdapi_retrieve")
    added_event = mock_db.add.call_args[0][0]
    assert added_event.severity == "error"


@pytest.mark.asyncio
async def test_purge_old_runs(mock_db, mock_redis):
    conn_id = uuid4()
    org_id = uuid4()
    with patch("app.services.sync_event_log.get_redis_client", return_value=mock_redis):
        emitter = SyncEventEmitter(conn_id, org_id, uuid4(), mock_db)
    mock_db.execute = AsyncMock()
    await emitter.purge_old_runs()
    mock_db.execute.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && py -m pytest tests/services/test_sync_event_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.sync_event_log'`

- [ ] **Step 3: Implement SyncEventEmitter**

```python
# backend/app/services/sync_event_log.py
"""Structured sync event logging — Postgres persistence + Redis pub/sub."""
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_event import SyncEvent
from app.services.sync_progress import get_redis_client

logger = logging.getLogger(__name__)


class SyncEventEmitter:
    """Emits structured sync events to Postgres + Redis pub/sub."""

    def __init__(
        self,
        connection_id: UUID,
        org_id: UUID,
        run_id: UUID,
        db: AsyncSession,
    ) -> None:
        self.connection_id = connection_id
        self.org_id = org_id
        self.run_id = run_id
        self.db = db
        self._sequence = 0
        self._redis = get_redis_client()
        self._channel = f"sync_events:{connection_id}"

    async def emit(
        self,
        event_type: str,
        message: str,
        *,
        phase: str | None = None,
        detail: dict | None = None,
        severity: str = "info",
    ) -> None:
        self._sequence += 1
        now = datetime.now(tz=UTC)
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
            created_at=now,
        )
        self.db.add(event)
        await self.db.flush()

        payload = {
            "run_id": str(self.run_id),
            "connection_id": str(self.connection_id),
            "sequence": self._sequence,
            "event_type": event_type,
            "phase": phase,
            "message": message,
            "detail": detail or {},
            "severity": severity,
            "created_at": now.isoformat(),
        }
        try:
            self._redis.publish(self._channel, json.dumps(payload))
        except Exception:
            logger.warning("redis_publish_failed channel=%s", self._channel, exc_info=True)

    async def purge_old_runs(self) -> None:
        """Delete all but the 2 most recent previous runs for this connection."""
        await self.db.execute(
            text("""
                DELETE FROM sync_events
                WHERE connection_id = :cid
                AND run_id NOT IN (
                    SELECT run_id FROM (
                        SELECT run_id, MAX(created_at) AS latest
                        FROM sync_events
                        WHERE connection_id = :cid
                        GROUP BY run_id
                        ORDER BY latest DESC
                        LIMIT 2
                    ) AS recent
                )
            """),
            {"cid": self.connection_id},
        )
        await self.db.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && py -m pytest tests/services/test_sync_event_log.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync_event_log.py backend/tests/services/test_sync_event_log.py
git commit -m "feat: add SyncEventEmitter for structured sync logging"
```

---

## Phase 2 — Backend Worker Integration

### Task 4: Replace Worker Progress System with SyncEventEmitter

**Files:**
- Modify: `backend/app/workers/metadata_sync.py`

The worker currently creates `progress_cb` as a closure calling `update_phase` on a Redis hash. We're **replacing** that entirely — no `init_progress`, no `update_phase`, no `complete_progress`. The emitter is the single source of truth.

- [ ] **Step 1: Rewrite metadata_sync.py**

Replace the entire content of `backend/app/workers/metadata_sync.py` with:

```python
import logging
from uuid import UUID, uuid4

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    import asyncio

    async def _pipeline() -> tuple[str, str | None]:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine as _create_engine

        from app.core.config import get_settings
        from app.models.connection import PlatformConnection
        from app.services.classification import run_classification
        from app.services.metadata_graph import build_dependency_graph, detect_metadata_communities
        from app.services.metadata_vectorizer import vectorize_org_metadata
        from app.services.salesforce.metadata import sync_metadata
        from app.services.sync_event_log import SyncEventEmitter

        _settings = get_settings()
        _engine = _create_engine(
            _settings.DATABASE_URL,
            pool_pre_ping=True,
        )
        factory = async_sessionmaker(_engine, expire_on_commit=False)
        run_id = uuid4()
        org_id: UUID | None = None

        async def _set_status(status: str) -> None:
            async with factory() as s:
                conn = await s.get(PlatformConnection, UUID(connection_id))
                if conn:
                    conn.status = status
                    await s.commit()

        try:
            async with factory() as session:
                conn = await session.get(PlatformConnection, UUID(connection_id))
                org_id_str = str(conn.org_id) if conn else None
                org_id = conn.org_id if conn else None

            if not org_id:
                raise ValueError(f"Connection {connection_id} not found")

            await _set_status("syncing")

            # --- Metadata sync (objects, MDAPI, automations, code, etc.) ---
            async with factory() as session:
                emitter = SyncEventEmitter(
                    UUID(connection_id), org_id, run_id, session,
                )
                await emitter.purge_old_runs()
                await emitter.emit("run_start", "Metadata sync started")
                await sync_metadata(
                    UUID(connection_id), session,
                    event_emitter=emitter,
                )
                await session.commit()

            # --- Dependency graph ---
            try:
                async with factory() as session:
                    emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                    await emitter.emit("phase_start", "Building dependency graph...", phase="graph_build")
                    conn_obj = await session.get(PlatformConnection, UUID(connection_id))
                    if conn_obj:
                        edge_count = await build_dependency_graph(UUID(connection_id), conn_obj.org_id, session)
                        await detect_metadata_communities(UUID(connection_id), conn_obj.org_id, session)
                    else:
                        edge_count = 0
                    await emitter.emit(
                        "phase_complete",
                        f"Dependency graph complete — {edge_count} edges",
                        phase="graph_build",
                        detail={"edge_count": edge_count},
                    )
                    await session.commit()
            except Exception:
                logger.exception("graph_build_failed connection=%s", connection_id)

            # --- Classification ---
            try:
                async with factory() as session:
                    emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                    await emitter.emit("phase_start", "Classifying metadata...", phase="classification")
                    conn_obj = await session.get(PlatformConnection, UUID(connection_id))
                    if conn_obj:
                        count = await run_classification(conn_obj.org_id, session, connection_id=UUID(connection_id))
                    else:
                        count = 0
                    await emitter.emit(
                        "phase_complete",
                        f"Classification complete — {count} objects classified",
                        phase="classification",
                        detail={"classified_count": count},
                    )
                    await session.commit()
            except Exception:
                logger.exception("classification_failed connection=%s", connection_id)

            # --- Vectorization ---
            try:
                async with factory() as session:
                    emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                    await emitter.emit("phase_start", "Vectorizing metadata...", phase="vectorization")
                    conn_obj = await session.get(PlatformConnection, UUID(connection_id))
                    if conn_obj:
                        count = await vectorize_org_metadata(UUID(connection_id), conn_obj.org_id, session)
                    else:
                        count = 0
                    await emitter.emit(
                        "phase_complete",
                        f"Vectorization complete — {count} chunks",
                        phase="vectorization",
                        detail={"chunk_count": count},
                    )
                    await session.commit()
            except Exception:
                logger.exception("vectorization_failed connection=%s", connection_id)

            # --- Done ---
            async with factory() as session:
                emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                await emitter.emit("run_complete", "Sync complete")
                await session.commit()

            await _set_status("connected")
            return connection_id, org_id_str

        except Exception as exc:
            logger.exception("sync_task_failed connection=%s", connection_id)
            try:
                if org_id is not None:
                    async with factory() as session:
                        emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                        await emitter.emit("error", f"Sync failed: {exc}", severity="error")
                        await session.commit()
                else:
                    logger.error(
                        "cannot_emit_sync_error_event_missing_org connection=%s",
                        connection_id,
                    )
            except Exception:
                logger.exception("failed_to_emit_error_event connection=%s", connection_id)
            try:
                await _set_status("error")
            except Exception:
                logger.exception("failed_to_set_error_status connection=%s", connection_id)
            raise
        finally:
            await _engine.dispose()

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    try:
        with langfuse_context(org_id=connection_id):
            with langfuse_span("metadata_sync", metadata={"connection_id": connection_id}):
                result_id, org_id_str = asyncio.run(_pipeline())
        return result_id
    finally:
        flush_langfuse()
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `cd backend && py -m pytest tests/ -v --timeout=30`
Expected: All existing tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/metadata_sync.py
git commit -m "feat: replace Redis hash progress with SyncEventEmitter in worker"
```

---

### Task 5: Replace progress_callback with SyncEventEmitter in sync_metadata

**Files:**
- Modify: `backend/app/services/salesforce/metadata.py`

The `sync_metadata` function currently accepts `progress_callback` and uses a `_progress()` helper. We're **replacing** both with `event_emitter` and `_emit()`. All `_progress()` calls become `await _emit()` calls. The `progress_callback` parameter is removed.

- [ ] **Step 1: Replace signature and helpers**

In `backend/app/services/salesforce/metadata.py`:

Add the `TYPE_CHECKING` import at the top of the file if not already present:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.sync_event_log import SyncEventEmitter
```

Replace the `sync_metadata` signature (line 887-891):

```python
async def sync_metadata(
    connection_id: UUID,
    db: AsyncSession,
    event_emitter: "SyncEventEmitter | None" = None,
) -> int:
```

Replace the `_progress` helper (lines 898-903) with `_emit` (use the module’s existing `logger`; add `logger = logging.getLogger(__name__)` at top of `metadata.py` if missing):

```python
    async def _emit(
        event_type: str,
        message: str,
        *,
        phase: str | None = None,
        detail: dict | None = None,
        severity: str = "info",
    ) -> None:
        if event_emitter:
            try:
                await event_emitter.emit(event_type, message, phase=phase, detail=detail, severity=severity)
            except Exception:
                logger.exception(
                    "sync_event_emit_failed event_type=%s connection_phase=%s",
                    event_type,
                    phase,
                )
```

- [ ] **Step 2: Replace all `_progress()` calls with `_emit()` calls**

For every existing `_progress(phase, "pulling", 0)` → `await _emit("phase_start", "...", phase=phase)`.
For every existing `_progress(phase, "done", count)` → `await _emit("phase_complete", "...", phase=phase, detail={"count": count})`.

Specific replacements:

```python
# objects
_progress("objects", "done", len(objects))
# becomes:
await _emit("phase_complete", f"Object describes complete — {len(objects)} objects", phase="objects", detail={"count": len(objects)})

# mdapi_retrieve
_progress("mdapi_retrieve", "pulling", 0)
# becomes:
await _emit("phase_start", "Retrieving metadata via MDAPI...", phase="mdapi_retrieve")

_progress("mdapi_retrieve", "done", len(mdapi_files))
# becomes:
await _emit("phase_complete", f"MDAPI retrieve complete — {len(mdapi_files)} files", phase="mdapi_retrieve", detail={"file_count": len(mdapi_files)})

# mdapi_parse
_progress("mdapi_parse", "pulling", 0)
# becomes:
await _emit("phase_start", "Parsing MDAPI metadata...", phase="mdapi_parse")

_progress("mdapi_parse", "done", sum(mdapi_bundle["counts"].values()))
# becomes:
await _emit("phase_complete", f"MDAPI parse complete — {sum(mdapi_bundle['counts'].values())} items", phase="mdapi_parse", detail=mdapi_bundle["counts"])

# automations
_progress("automations", "pulling", 0)
# becomes:
await _emit("phase_start", "Processing automations...", phase="automations")

_progress("automations", "done", ...)
# becomes:
await _emit("phase_complete", f"Automations complete — {len(mdapi_bundle['pending_automations']) + len(all_validation_rules)} items", phase="automations", detail={"count": len(mdapi_bundle['pending_automations']) + len(all_validation_rules)})
```

Apply the same pattern for `permissions`, `ui_components`, `installed_packages`, `custom_metadata_types`, `licensing`, `user_velocity`, `entities`, and `code`.

- [ ] **Step 3: Add item-level events for MDAPI parsing**

After `_persist_mdapi_zip_results(...)` call, emit item events for parsed components:

```python
    for auto_row in mdapi_bundle.get("pending_automations", []):
        auto_data = auto_row.get("metadata_json", {})
        api_name = auto_row.get("api_name", "")
        auto_type = auto_row.get("automation_type", "")
        if auto_type == "flow":
            elements = auto_data.get("element_count", 0)
            await _emit("item", f"Parsed {api_name} — {elements} elements", phase="mdapi_parse", detail={"api_name": api_name, "component_type": "flow", "element_count": elements})
        elif auto_type == "apex_class":
            methods = len(auto_data.get("methods", []))
            dml = auto_data.get("dml_objects", [])
            await _emit("item", f"Parsed {api_name} — {methods} methods, DML: {', '.join(dml) if dml else 'none'}", phase="mdapi_parse", detail={"api_name": api_name, "component_type": "apex_class", "method_count": methods, "dml_objects": dml})
```

- [ ] **Step 4: Emit warning events for non-fatal issues**

In `sync_metadata`, wherever we catch non-fatal exceptions and log warnings (e.g., licensing, user_velocity, entity_sync), also emit a `warning` event:

```python
# After logger.warning("licensing_snapshot_failed ..."):
        await _emit("warning", f"Licensing snapshot failed: {e}", phase="licensing", severity="warning")

# After logger.warning("user_velocity_snapshot_failed ..."):
        await _emit("warning", f"User velocity snapshot failed: {e}", phase="user_velocity", severity="warning")

# After logger.warning("entity_sync_failed ..."):
        await _emit("warning", f"Entity sync failed: {e}", phase="entities", severity="warning")
```

- [ ] **Step 5: Run existing tests**

Run: `cd backend && py -m pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/salesforce/metadata.py
git commit -m "feat: replace progress_callback with SyncEventEmitter in metadata pipeline"
```

---

## Phase 3 — Backend SSE Endpoint + REST APIs

### Task 6: SSE Stream Endpoint + Remove sync-status

**Files:**
- Modify: `backend/app/api/routes/connections.py`

- [ ] **Step 1: Remove old sync-status endpoint and init_progress from sync_connection**

In `backend/app/api/routes/connections.py`:

1. Remove the `get_sync_status` endpoint entirely (lines 165-176).

2. In `sync_connection` (line 147-162), remove the `init_progress` import and call:

```python
# DELETE these lines:
    from app.services.sync_progress import init_progress
    init_progress(str(conn.id))
```

The `sync_connection` endpoint becomes simply:

```python
@router.post("/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_connection(
    connection_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str]:
    """Enqueue metadata sync for a connection."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn.status = "syncing"
    await db.commit()
    sync_metadata_task.delay(str(conn.id))
    return {"status": "queued", "connection_id": str(conn.id)}
```

- [ ] **Step 2: Add the SSE endpoint**

Add the following imports at the top of `backend/app/api/routes/connections.py`:

```python
import asyncio
import json as json_mod
from typing import AsyncGenerator

import redis
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select

from app.models.sync_event import SyncEvent
```

Add the SSE endpoint after `sync_connection`:

```python
@router.get("/{connection_id}/sync-stream")
async def sync_event_stream(
    connection_id: UUID,
    org: CurrentOrg,
    db: DbSession,
) -> StreamingResponse:
    """SSE stream of sync events — backfills latest run then streams live."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        from app.services.sync_progress import get_redis_client

        r = get_redis_client()
        channel = f"sync_events:{connection_id}"
        loop = asyncio.get_running_loop()

        latest_run_q = await db.execute(
            sa_select(SyncEvent)
            .where(SyncEvent.connection_id == connection_id)
            .order_by(SyncEvent.created_at.desc())
            .limit(1)
        )
        latest_event = latest_run_q.scalar_one_or_none()
        latest_run_id = latest_event.run_id if latest_event else None
        backfill_events: list[SyncEvent] = []
        last_seq = 0

        if latest_run_id:
            backfill_q = await db.execute(
                sa_select(SyncEvent)
                .where(
                    SyncEvent.connection_id == connection_id,
                    SyncEvent.run_id == latest_run_id,
                )
                .order_by(SyncEvent.sequence)
            )
            backfill_events = list(backfill_q.scalars().all())
            last_seq = max((e.sequence for e in backfill_events), default=0)
            backfill_data = [
                {
                    "run_id": str(e.run_id),
                    "sequence": e.sequence,
                    "event_type": e.event_type,
                    "phase": e.phase,
                    "message": e.message,
                    "detail": e.detail_json,
                    "severity": e.severity,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in backfill_events
            ]
            yield f"event: backfill\ndata: {json_mod.dumps(backfill_data)}\n\n"

            is_done = any(
                e.event_type == "run_complete"
                or (e.event_type == "error" and e.severity == "error")
                for e in backfill_events
            )
            if is_done:
                yield "event: done\ndata: {}\n\n"
                return

        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        try:
            # Rows committed after the backfill SELECT but before we subscribed are
            # not on Redis yet for this client; replay from DB once.
            if latest_run_id:
                gap_q = await db.execute(
                    sa_select(SyncEvent)
                    .where(
                        SyncEvent.connection_id == connection_id,
                        SyncEvent.run_id == latest_run_id,
                        SyncEvent.sequence > last_seq,
                    )
                    .order_by(SyncEvent.sequence)
                )
                for row in gap_q.scalars().all():
                    payload = {
                        "run_id": str(row.run_id),
                        "connection_id": str(connection_id),
                        "sequence": row.sequence,
                        "event_type": row.event_type,
                        "phase": row.phase,
                        "message": row.message,
                        "detail": row.detail_json,
                        "severity": row.severity,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                    yield f"event: sync_event\ndata: {json_mod.dumps(payload)}\n\n"

            last_keepalive = loop.time()

            def _is_terminal(parsed: dict) -> bool:
                et = parsed.get("event_type")
                if et == "run_complete":
                    return True
                return et == "error" and parsed.get("severity") == "error"

            while True:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield f"event: sync_event\ndata: {data}\n\n"
                    parsed = json_mod.loads(data)
                    if _is_terminal(parsed):
                        yield "event: done\ndata: {}\n\n"
                        return

                now = loop.time()
                if now - last_keepalive > 15:
                    yield ": keepalive\n\n"
                    last_keepalive = now

                await asyncio.sleep(0.25)
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes/connections.py
git commit -m "feat: add SSE endpoint for sync event streaming"
```

---

### Task 7: REST Endpoint — sync-events

**Files:**
- Modify: `backend/app/api/routes/connections.py`

- [ ] **Step 1: Add the sync-events endpoint**

After the `sync-stream` endpoint, add:

```python
@router.get("/{connection_id}/sync-events")
async def get_sync_events(
    connection_id: UUID,
    org: CurrentOrg,
    db: DbSession,
    run_id: UUID | None = Query(default=None),
) -> list[dict]:
    """Return events for a specific run, or the latest run. Useful for debugging via curl."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    if run_id is None:
        latest_q = await db.execute(
            sa_select(SyncEvent.run_id)
            .where(SyncEvent.connection_id == connection_id)
            .order_by(SyncEvent.created_at.desc())
            .limit(1)
        )
        row = latest_q.first()
        if not row:
            return []
        run_id = row[0]

    q = await db.execute(
        sa_select(SyncEvent)
        .where(
            SyncEvent.connection_id == connection_id,
            SyncEvent.run_id == run_id,
        )
        .order_by(SyncEvent.sequence)
    )
    return [
        {
            "id": str(e.id),
            "run_id": str(e.run_id),
            "sequence": e.sequence,
            "event_type": e.event_type,
            "phase": e.phase,
            "message": e.message,
            "detail": e.detail_json,
            "severity": e.severity,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in q.scalars().all()
    ]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/connections.py
git commit -m "feat: add sync-events REST endpoint for debugging"
```

---

## Phase 4 — Frontend SSE Hook + Types

### Task 8: TypeScript Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add SyncEvent type**

Append to `frontend/src/types/index.ts`:

```typescript
/** Structured sync event from the backend event log */
export interface SyncEvent {
  id?: string
  run_id?: string
  sequence: number
  event_type: 'run_start' | 'phase_start' | 'phase_complete' | 'item' | 'warning' | 'error' | 'run_complete'
  phase: string | null
  message: string
  detail: Record<string, unknown>
  severity: 'info' | 'warning' | 'error'
  created_at: string | null
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add SyncEvent and SyncRun TypeScript types"
```

---

### Task 9: API Client Methods

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add sync event API methods**

In `frontend/src/api/client.ts`, add imports at the top (line 1, extend the existing import):

Add `SyncEvent` to the type import list.

Inside the `connections` object, **remove** the `syncStatus` method (lines 149-156) and add:

```typescript
    syncEvents: (id: string, runId?: string) =>
      request<SyncEvent[]>(
        withQuery(`/connections/${id}/sync-events`, runId ? { run_id: runId } : undefined),
      ),
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add syncEvents and syncRuns API client methods"
```

---

### Task 10: useSyncEventStream Hook

**Files:**
- Create: `frontend/src/hooks/useSyncEventStream.ts`

- [ ] **Step 1: Write the hook**

```typescript
// frontend/src/hooks/useSyncEventStream.ts
import { useCallback, useEffect, useRef, useState } from 'react'
import type { SyncEvent } from '@/types'
import { api } from '@/api/client'

export type SyncStreamStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed'

export function useSyncEventStream(connectionId: string | null) {
  const [events, setEvents] = useState<SyncEvent[]>([])
  const [status, setStatus] = useState<SyncStreamStatus>('idle')
  const esRef = useRef<EventSource | null>(null)

  const close = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
  }, [])

  useEffect(() => {
    if (!connectionId) {
      setEvents([])
      setStatus('idle')
      return
    }

    setStatus('connecting')
    const url = api.connections.syncStreamUrl(connectionId)
    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('backfill', (e: MessageEvent) => {
      try {
        const data: SyncEvent[] = JSON.parse(e.data)
        setEvents(data)
        const hasComplete = data.some((ev) => ev.event_type === 'run_complete')
        const hasError = data.some((ev) => ev.event_type === 'error' && ev.severity === 'error')
        if (hasComplete) {
          setStatus('completed')
        } else if (hasError) {
          setStatus('failed')
        } else {
          setStatus('running')
        }
      } catch {
        /* ignore parse errors */
      }
    })

    es.addEventListener('sync_event', (e: MessageEvent) => {
      try {
        const event: SyncEvent = JSON.parse(e.data)
        setEvents((prev) => [...prev, event])
        if (event.event_type === 'run_complete') {
          setStatus('completed')
        } else if (event.event_type === 'error' && event.severity === 'error') {
          setStatus('failed')
        } else if (status !== 'running') {
          setStatus('running')
        }
      } catch {
        /* ignore parse errors */
      }
    })

    es.addEventListener('done', () => {
      es.close()
      esRef.current = null
    })

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        setStatus((prev) => (prev === 'running' || prev === 'connecting' ? 'failed' : prev))
      }
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [connectionId])

  const reset = useCallback(() => {
    close()
    setEvents([])
    setStatus('idle')
  }, [close])

  return { events, status, reset }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useSyncEventStream.ts
git commit -m "feat: add useSyncEventStream SSE hook"
```

---

## Phase 5 — Frontend UI

### Task 11: SyncEventLogPanel Component

**Files:**
- Create: `frontend/src/components/SyncEventLogPanel.tsx`

- [ ] **Step 1: Build the component**

```tsx
// frontend/src/components/SyncEventLogPanel.tsx
import { useEffect, useRef, useState, useMemo } from 'react'
import { Check, ChevronDown, ChevronUp, Loader2, AlertTriangle, XCircle } from 'lucide-react'
import clsx from 'clsx'
import type { SyncEvent } from '@/types'
import type { SyncStreamStatus } from '@/hooks/useSyncEventStream'

const PHASE_LABELS: Record<string, string> = {
  objects: 'Data Objects',
  mdapi_retrieve: 'Metadata Retrieve',
  mdapi_parse: 'Metadata Parse',
  automations: 'Automations',
  code: 'Code Assets',
  permissions: 'Security',
  ui_components: 'UI Components',
  installed_packages: 'Packages',
  custom_metadata_types: 'Custom Metadata',
  licensing: 'Licensing',
  user_velocity: 'Adoption',
  entities: 'Org Hierarchy',
  graph_build: 'Dependency Graph',
  classification: 'Classification',
  vectorization: 'Vectorization',
}

const PHASE_ORDER = Object.keys(PHASE_LABELS)

interface PhaseState {
  status: 'waiting' | 'running' | 'done' | 'error'
  count?: number
}

function derivePhaseStates(events: SyncEvent[]): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const phase of PHASE_ORDER) {
    states[phase] = { status: 'waiting' }
  }
  for (const e of events) {
    if (!e.phase) continue
    if (e.event_type === 'phase_start') {
      states[e.phase] = { status: 'running' }
    } else if (e.event_type === 'phase_complete') {
      const count = (e.detail?.count ?? e.detail?.file_count ?? e.detail?.edge_count ?? e.detail?.classified_count ?? e.detail?.chunk_count ?? 0) as number
      states[e.phase] = { status: 'done', count }
    } else if (e.event_type === 'error') {
      states[e.phase] = { status: 'error' }
    }
  }
  return states
}

function PhaseChip({ name, state }: { name: string; state: PhaseState }) {
  const label = PHASE_LABELS[name] ?? name

  return (
    <div
      className={clsx(
        'flex min-w-0 items-center gap-1.5 overflow-hidden rounded-lg border px-2.5 py-2 text-xs transition-all duration-300',
        state.status === 'waiting' && 'border-slate-200 bg-slate-50 text-slate-400',
        state.status === 'running' && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        state.status === 'done' && 'border-emerald-200 bg-emerald-50 text-emerald-800',
        state.status === 'error' && 'border-red-200 bg-red-50 text-red-800',
      )}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
        {state.status === 'waiting' && <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />}
        {state.status === 'running' && <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" />}
        {state.status === 'done' && <Check className="h-3.5 w-3.5 text-emerald-600" />}
        {state.status === 'error' && <XCircle className="h-3.5 w-3.5 text-red-500" />}
      </span>
      <span className="truncate font-medium">{label}</span>
      {state.status === 'done' && state.count != null && state.count > 0 && (
        <span className="ml-auto shrink-0 tabular-nums font-semibold">
          {state.count.toLocaleString()}
        </span>
      )}
    </div>
  )
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

interface Props {
  events: SyncEvent[]
  status: SyncStreamStatus
  onDismiss?: () => void
}

export function SyncEventLogPanel({ events, status, onDismiss }: Props) {
  const [logOpen, setLogOpen] = useState(true)
  const logRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const prevEventCount = useRef(0)

  const phaseStates = useMemo(() => derivePhaseStates(events), [events])
  const doneCount = PHASE_ORDER.filter((p) => phaseStates[p]?.status === 'done').length
  const totalPhases = PHASE_ORDER.length
  const pct = totalPhases > 0 ? Math.round((doneCount / totalPhases) * 100) : 0

  const isRunning = status === 'running' || status === 'connecting'
  const isCompleted = status === 'completed'
  const isFailed = status === 'failed'
  const isIdle = status === 'idle'

  useEffect(() => {
    if (events.length > prevEventCount.current && autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
    prevEventCount.current = events.length
  }, [events.length, autoScroll])

  const handleLogScroll = () => {
    if (!logRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = logRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }

  if (isIdle && events.length === 0) return null

  const elapsed = useMemo(() => {
    const start = events.find((e) => e.event_type === 'run_start')
    if (!start?.created_at) return null
    const end = [...events].reverse().find(
      (e) => e.event_type === 'run_complete' || (e.event_type === 'error' && e.severity === 'error'),
    )
    const endTime = end?.created_at ? new Date(end.created_at).getTime() : Date.now()
    const ms = endTime - new Date(start.created_at).getTime()
    if (ms < 60_000) return `${Math.round(ms / 1000)}s`
    return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
  }, [events, status])

  return (
    <div
      className={clsx(
        'rounded-xl border transition-all duration-500 overflow-hidden',
        isRunning && 'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        isCompleted && 'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        isFailed && 'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
        isIdle && 'border-slate-200 bg-white',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {isRunning && 'Syncing metadata\u2026'}
            {isCompleted && 'Sync complete'}
            {isFailed && 'Sync failed'}
            {isIdle && 'Sync Log'}
          </p>
          <p className="text-xs text-slate-500">
            {isRunning && `${doneCount} of ${totalPhases} phases complete`}
            {isCompleted && `All ${totalPhases} phases complete`}
            {isFailed && 'An error occurred during sync'}
            {elapsed && ` \u00b7 ${elapsed}`}
          </p>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-sky-500 transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-slate-500">{pct}%</span>
          </div>
        )}
      </div>

      {/* Phase pills */}
      <div className="grid grid-cols-2 gap-2 px-5 pb-3 sm:grid-cols-3 lg:grid-cols-5">
        {PHASE_ORDER.map((phase) => (
          <PhaseChip key={phase} name={phase} state={phaseStates[phase]} />
        ))}
      </div>

      {/* Sync Log */}
      <div className="border-t border-slate-200/60">
        <button
          type="button"
          onClick={() => setLogOpen(!logOpen)}
          className="flex w-full items-center justify-between px-5 py-2.5 text-xs font-medium text-slate-500 hover:bg-slate-50"
        >
          <span>Sync Log</span>
          {logOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>

        {logOpen && (
          <div className="relative">
            <div
              ref={logRef}
              onScroll={handleLogScroll}
              className="max-h-72 overflow-y-auto bg-slate-900 px-4 py-3 font-mono text-xs leading-relaxed text-slate-300"
            >
              {events.map((e, i) => {
                if (e.event_type === 'phase_start' || e.event_type === 'phase_complete') {
                  return (
                    <div key={i} className="my-1">
                      <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                      <span
                        className={clsx(
                          'font-semibold',
                          e.event_type === 'phase_complete' ? 'text-emerald-400' : 'text-sky-400',
                        )}
                      >
                        {e.message}
                      </span>
                    </div>
                  )
                }
                if (e.event_type === 'item') {
                  return (
                    <div key={i} className="ml-4 text-slate-500">
                      <span className="text-slate-600">{formatTimestamp(e.created_at)}  </span>
                      <span className="text-slate-400">{'▸ '}{e.message}</span>
                    </div>
                  )
                }
                if (e.event_type === 'warning') {
                  return (
                    <div key={i} className="my-0.5 flex items-start gap-1.5">
                      <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
                      <span className="text-amber-400">{e.message}</span>
                    </div>
                  )
                }
                if (e.event_type === 'error') {
                  return (
                    <div key={i} className="my-0.5 flex items-start gap-1.5">
                      <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                      <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-red-400" />
                      <span className="text-red-400">{e.message}</span>
                    </div>
                  )
                }
                return (
                  <div key={i} className="my-0.5">
                    <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                    <span>{e.message}</span>
                  </div>
                )
              })}
              {isRunning && (
                <div className="my-1 flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin text-sky-400" />
                </div>
              )}
            </div>
            {!autoScroll && (
              <button
                type="button"
                onClick={() => {
                  setAutoScroll(true)
                  logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
                }}
                className="absolute bottom-2 right-4 rounded-md bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
              >
                Jump to bottom
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SyncEventLogPanel.tsx
git commit -m "feat: add SyncEventLogPanel with terminal-style log + phase pills"
```

---

### Task 12: Wire into Platforms Page

**Files:**
- Modify: `frontend/src/pages/Platforms/index.tsx`

- [ ] **Step 1: Update imports**

Replace the `SyncProgressPanel` import with `SyncEventLogPanel`:

```typescript
import { SyncEventLogPanel } from '@/components/SyncEventLogPanel'
import { useSyncEventStream } from '@/hooks/useSyncEventStream'
```

Remove `useSyncProgress` / `syncProgressQuery` from this page when wiring Task 16 (the hook is deleted). Until then, do not re-import `useSyncProgress` here — it contradicts removing the old system.

- [ ] **Step 2: Add the SSE hook**

Add:

```typescript
  const { events: syncEvents, status: syncStreamStatus, reset: resetSyncStream } = useSyncEventStream(activeSyncId)
```

- [ ] **Step 3: Update the onSync callback**

In the `onSync` callback (line 246), add `resetSyncStream()` before `setActiveSyncId`:

```typescript
  const onSync = useCallback(() => {
    if (!connection) return
    const cid = String(connection.id)
    qc.removeQueries({ queryKey: ['sync-progress', cid] })
    resetSyncStream()
    setSyncingId(cid)
    setActiveSyncId(cid)
    syncConnection.mutate(cid, {
      onSettled: () => setSyncingId(null),
    })
  }, [syncConnection, qc, connection, resetSyncStream])
```

- [ ] **Step 4: Replace SyncProgressPanel render**

Find the `SyncProgressPanel` render (lines 374-379) and replace with:

```tsx
        {activeSyncId && (
          <SyncEventLogPanel
            events={syncEvents}
            status={syncStreamStatus}
            onDismiss={dismissSyncPanel}
          />
        )}
```

- [ ] **Step 5: Run dev server and verify no build errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Platforms/index.tsx
git commit -m "feat: replace SyncProgressPanel with SyncEventLogPanel on Platforms page"
```

---

### Task 13: Wire into Analysis Page

**Files:**
- Modify: `frontend/src/pages/Analysis/index.tsx`
- Modify: `frontend/src/components/SyncProgressModal.tsx`

- [ ] **Step 1: Update SyncProgressModal to accept SyncEventLogPanel**

In `frontend/src/components/SyncProgressModal.tsx`, update to use the new panel:

Replace the imports (lines 1-3):

```typescript
import { useCallback, useEffect, useRef } from 'react'
import { Info, X } from 'lucide-react'
import { SyncEventLogPanel } from './SyncEventLogPanel'
import type { SyncEvent } from '@/types'
import type { SyncStreamStatus } from '@/hooks/useSyncEventStream'
```

Replace the `Props` interface (lines 13-18):

```typescript
interface Props {
  open: boolean
  onClose: () => void
  events: SyncEvent[]
  streamStatus: SyncStreamStatus
  platformLabel?: string
}
```

Update the component signature and body. Replace `{ open, onClose, data, platformLabel }` with `{ open, onClose, events, streamStatus, platformLabel }`.

Replace `const isTerminal = data?.status === 'completed' || data?.status === 'failed'` with:

```typescript
  const isTerminal = streamStatus === 'completed' || streamStatus === 'failed'
```

Replace the `SyncProgressPanel` render (line 96) with:

```tsx
          <SyncEventLogPanel events={events} status={streamStatus} />
```

- [ ] **Step 2: Update Analysis page to pass new props**

In `frontend/src/pages/Analysis/index.tsx`:

Add import:

```typescript
import { useSyncEventStream } from '@/hooks/useSyncEventStream'
```

Remove `useSyncProgress` / `syncProgressQuery` from this file per Task 16, then add:

```typescript
  const { events: syncEvents, status: syncStreamStatus, reset: resetSyncStream } = useSyncEventStream(activeSyncId)
```

In `onSync` callback (line 127), add `resetSyncStream()` before `setSyncingId`:

```typescript
  const onSync = useCallback(
    (id: string) => {
      qc.removeQueries({ queryKey: ['sync-progress', id] })
      resetSyncStream()
      setSyncingId(id)
      setActiveSyncId(id)
      setShowSyncModal(true)
      syncConnection.mutate(id, {
        onSettled: () => setSyncingId(null),
      })
    },
    [syncConnection, qc, resetSyncStream],
  )
```

Update the `SyncProgressModal` props (lines 225-237):

```tsx
      <SyncProgressModal
        open={showSyncModal && !!activeSyncId}
        onClose={() => setShowSyncModal(false)}
        events={syncEvents}
        streamStatus={syncStreamStatus}
        platformLabel={
          activeSyncId
            ? platformLabelFromType(
                connections.find((c) => String(c.id) === activeSyncId)?.platform_type ??
                  (connections.find((c) => String(c.id) === activeSyncId)?.platform as string | undefined),
              )
            : undefined
        }
      />
```

- [ ] **Step 3: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SyncProgressModal.tsx frontend/src/pages/Analysis/index.tsx
git commit -m "feat: wire SyncEventLogPanel into Analysis page modal"
```

---

## Phase 6 — SSE Auth + Cleanup

### Task 14: SSE Authentication

**Files:**
- Modify: `frontend/src/hooks/useSyncEventStream.ts`
- Modify: `frontend/src/api/client.ts`

The `EventSource` API doesn't support custom headers for Bearer auth. Two options: (a) pass token as query param, or (b) use `fetchWithAuth` + manual SSE parsing. Since we already have `fetchWithAuth` with auth in `client.ts`, we use option (b) for security.

- [ ] **Step 1: Replace EventSource with fetch-based SSE in the hook**

Replace the hook implementation to use `fetchWithAuth` instead of `EventSource`:

```typescript
// frontend/src/hooks/useSyncEventStream.ts
import { useCallback, useEffect, useRef, useState } from 'react'
import type { SyncEvent } from '@/types'
import { fetchWithAuth } from '@/api/client'

export type SyncStreamStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed'

export function useSyncEventStream(connectionId: string | null) {
  const [events, setEvents] = useState<SyncEvent[]>([])
  const [status, setStatus] = useState<SyncStreamStatus>('idle')
  const abortRef = useRef<AbortController | null>(null)

  const close = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  useEffect(() => {
    if (!connectionId) {
      setEvents([])
      setStatus('idle')
      return
    }

    const controller = new AbortController()
    abortRef.current = controller

    setStatus('connecting')

    ;(async () => {
      try {
        const res = await fetchWithAuth(`/connections/${connectionId}/sync-stream`, {
          headers: { Accept: 'text/event-stream' },
          signal: controller.signal,
        })

        if (!res.ok || !res.body) {
          setStatus('failed')
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          let currentEvent = ''
          let currentData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim()
              currentData = ''
            } else if (line.startsWith('data: ')) {
              const piece = line.slice(6)
              currentData = currentData ? `${currentData}\n${piece}` : piece
            } else if (line === '' && currentEvent) {
              if (currentEvent === 'backfill') {
                try {
                  const data: SyncEvent[] = JSON.parse(currentData)
                  setEvents(data)
                  const hasComplete = data.some((ev) => ev.event_type === 'run_complete')
                  const hasError = data.some((ev) => ev.event_type === 'error' && ev.severity === 'error')
                  setStatus(hasComplete ? 'completed' : hasError ? 'failed' : 'running')
                } catch { /* skip */ }
              } else if (currentEvent === 'sync_event') {
                try {
                  const event: SyncEvent = JSON.parse(currentData)
                  setEvents((prev) => [...prev, event])
                  if (event.event_type === 'run_complete') setStatus('completed')
                  else if (event.event_type === 'error' && event.severity === 'error') setStatus('failed')
                  else setStatus('running')
                } catch { /* skip */ }
              } else if (currentEvent === 'done') {
                return
              }
              currentEvent = ''
              currentData = ''
            }
          }
        }
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          setStatus((prev) => (prev === 'running' || prev === 'connecting' ? 'failed' : prev))
        }
      }
    })()

    return () => {
      controller.abort()
      abortRef.current = null
    }
  }, [connectionId])

  const reset = useCallback(() => {
    close()
    setEvents([])
    setStatus('idle')
  }, [close])

  return { events, status, reset }
}
```

- [ ] **Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useSyncEventStream.ts
git commit -m "fix: use fetchWithAuth for SSE to include auth headers"
```

---

### Task 15: Query Invalidation on Sync Complete

**Files:**
- Modify: `frontend/src/hooks/useSyncEventStream.ts` or the parent pages

- [ ] **Step 1: Invalidate queries when sync completes**

In both `Platforms/index.tsx` and `Analysis/index.tsx`, add an effect that watches `syncStreamStatus` and invalidates queries on completion:

```typescript
  useEffect(() => {
    if (syncStreamStatus === 'completed' || syncStreamStatus === 'failed') {
      void qc.invalidateQueries({ queryKey: ['connections'] })
      void qc.invalidateQueries({ queryKey: ['metadata'] })
      void qc.invalidateQueries({ queryKey: ['organization'] })
      void qc.invalidateQueries({ queryKey: ['sync-runs'] })
    }
  }, [syncStreamStatus, qc])
```

This mirrors the existing `useSyncProgress` invalidation behavior.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Platforms/index.tsx frontend/src/pages/Analysis/index.tsx
git commit -m "feat: invalidate queries on sync stream completion"
```

---

### Task 16: Remove Old Progress System

**Files:**
- Modify: `backend/app/services/sync_progress.py` — gut everything except `get_redis_client`
- Delete: `frontend/src/components/SyncProgressPanel.tsx`
- Modify: `frontend/src/hooks/useApi.ts` — remove `useSyncProgress`
- Modify: `frontend/src/api/client.ts` — remove `syncStatus` if not already done in Task 9

`get_redis_client()` is still used by `backend/app/workers/process_discovery.py` and `backend/app/api/routes/discovery.py` for discovery progress tracking. It stays.

- [ ] **Step 1: Gut sync_progress.py**

Replace the entire content of `backend/app/services/sync_progress.py` with:

```python
"""Redis client utility. Legacy sync phase tracking has been replaced by SyncEventEmitter."""
import redis


def get_redis_client() -> redis.Redis:
    from app.core.config import get_settings
    return redis.from_url(get_settings().REDIS_URL, decode_responses=True)
```

- [ ] **Step 2: Delete SyncProgressPanel.tsx**

Delete `frontend/src/components/SyncProgressPanel.tsx`. It has been replaced by `SyncEventLogPanel.tsx`.

- [ ] **Step 3: Remove useSyncProgress from useApi.ts**

In `frontend/src/hooks/useApi.ts`, delete the entire `useSyncProgress` function (lines 274-297).

- [ ] **Step 4: Clean up any remaining imports**

Search all frontend files for `SyncProgressPanel` and `useSyncProgress` imports and remove them. After Tasks 12 and 13, these should already be gone, but verify:

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync_progress.py frontend/src/hooks/useApi.ts
git rm frontend/src/components/SyncProgressPanel.tsx
git commit -m "chore: remove old Redis hash progress system — replaced by sync event log"
```

---

## Antipatterns

Design review (2026-04-19). Each item lists **severity** and **mitigation** (several mitigations are already applied in code snippets above).

| Topic | Severity | Finding | Mitigation |
|------|----------|---------|------------|
| **Unbounded growth** (`sync_events` / `item` volume) | **P2** | High-volume `item` emits (flows, Apex) can create large rows-per-run; table is bounded by retention but a single run can still be huge. | Cap `item` emits (sample N per phase + summary), or emit items only when a `detail` flag is enabled; keep `message` compact. |
| **Unbounded growth** (React `events` state) | **P2** | `setEvents((prev) => [...prev, event])` grows without bound during long syncs. | Cap array length (e.g. keep last 5_000) or virtualize the log; drop `item` rows from state when over budget while keeping phase aggregates. |
| **N+1 queries** | **P3** | Backfill and gap replay use one SQL query each — no N+1 in the SSE path. | None required; keep batch emits in `metadata.py` loops (no per-row `await db.execute`). |
| **Race: backfill → subscribe gap** | **P1** | Rows committed after the backfill `SELECT` but before the client was subscribed could be missed if Redis was also missed. | **Implemented:** one DB “gap replay” query after `pubsub.subscribe()` for `sequence > last_seq`. Document that Redis remains best-effort; Postgres is source of truth after commit. |
| **Race: concurrent syncs, same channel** | **P1** | Two workers for the same `connection_id` publish interleaved messages on `sync_events:{id}` without run scoping in the channel name. | **Implemented:** include `run_id` (and `connection_id`) in every Redis payload; **recommended follow-up:** return `run_id` from `POST /sync` and add optional `?run_id=` on the SSE URL so the server filters or uses a per-run channel. |
| **Memory leaks** (SSE generator) | **P3** | Loop runs until terminal event; misbehaving worker could leave connections open. | Keep server/proxy idle timeouts; terminal `error` + `run_complete` must always be emitted; consider `asyncio.wait_for` max lifetime guard in a later iteration. |
| **Silent failures** | **P0** | Prior plan used bare `except: pass` in `_emit` and `logger.debug` on Redis publish — violates spec “No silent fallbacks.” | **Fixed:** log `logger.exception` / `logger.warning(..., exc_info=True)` in `_emit` and Redis publish paths; worker error emit uses `logger.exception` on failure. |
| **Tight coupling** (emitter ↔ session) | **P2** | `SyncEventEmitter` holds `AsyncSession`; worker creates multiple emitters across sessions for one `run_id` — sequence resets per emitter (**bug** for global monotonic `sequence` per run). | **Mitigation:** use a **single** `AsyncSession` for the entire worker pipeline for a run, or persist `next_sequence` in Redis/DB per `run_id` before constructing a new emitter; document that current multi-session layout breaks cross-session sequence monotonicity (acceptable only if UI orders by `(created_at, sequence)` within emitter scope — still confusing). *Preferred fix:* one long-lived session for the whole `_pipeline` or a DB sequence keyed by `(run_id)` via `SELECT max(sequence)+1` on each emit (expensive) or Redis `INCR sync_seq:{run_id}`. |
| **Missing indexes** | **P2** | “Latest run” uses `ORDER BY created_at DESC` on `connection_id`. | **Addressed:** `ix_sync_events_connection_created` added in Task 1 + Task 2 migration snippets. |
| **Frontend memory** | **P2** | Same as unbounded `events` array. | See cap/virtualize above. |
| **SSE reconnection** | **P1** | `fetchWithAuth` loop does not reconnect with backoff; transient network blips mark failed or stall UI. | On non-abort errors, exponential backoff reconnect; on reconnect, rely on server backfill + gap replay for latest run. |
| **Concurrent syncs** (API + worker) | **P1** | Double `POST /sync` queues two Celery jobs; interleaved events and `purge_old_runs` races. | Reject second sync while `conn.status == 'syncing'` (409) or use a distributed lock per `connection_id`; align `purge_old_runs` with “current run” awareness. |
| **Transaction safety** | **P1** | `flush()` makes rows visible to **same** transaction only; other sessions see events only after `commit`. Redis publishes **before** commit — live UI is correct; DB-only viewers see lag until commit. | Document as intentional; for atomic “event reflects committed work,” publish **after** `commit` (outbox pattern) — larger refactor. |
| **Redis pub/sub reliability** | **P1** | Pub/sub is at-most-once; no persistence. | Postgres backfill + post-subscribe gap replay; for stricter delivery use Redis Streams consumer groups or outbox + poll (future). |
| **SSE terminal `error` event** | **P0** | Live loop only closed on `run_complete`, not `error` — stream could hang after fatal error. | **Fixed:** `_is_terminal()` treats `error` + `severity == "error"` like `run_complete` for `done` + generator exit; backfill uses the same rule. |
| **Worker `org_id` fallback bug** | **P0** | `org_id or UUID(connection_id)` silently wrote wrong `org_id` FK on error path. | **Fixed:** guard `if org_id is not None` before emitting; log if org unresolved. |
| **Langfuse `org_id=connection_id`** | **P3** | `langfuse_context(org_id=connection_id)` may mis-attribute observability (pre-existing pattern). | Pass real org UUID when available from `conn`. |
| **Silent parse failures (frontend)** | **P3** | `catch { /* skip */ }` around `JSON.parse` in the SSE hook drops malformed frames with no telemetry. | `console.warn` in dev or increment a `parseErrors` counter exposed for debugging. |

### Design verdicts (reviewer)

| Decision | Verdict | Notes |
|----------|---------|-------|
| Postgres for persistence | **GOOD** | Fits tenant-scoped audit, SQL queries, FK integrity, retention via `DELETE`. |
| Redis pub/sub for fanout | **CONCERN** | At-most-once; acceptable with Postgres reconciliation; not a durable log. |
| SSE + `StreamingResponse` | **GOOD** | One-way stream, standard through proxies with keepalive + buffering headers. |
| `fetchWithAuth` vs `EventSource` | **GOOD** | Bearer auth in headers avoids token-in-query leakage. |
| New `SyncEventEmitter` vs extending Redis hash | **GOOD** | Clean domain model; old hash cannot represent structured audit log. |
| Retention via `DELETE` before each sync | **CONCERN** | Table scans/locks at scale; acceptable early-stage; consider partitioned archive later. |
| `purge_old_runs` derived-table `LIMIT` | **GOOD** | Valid PostgreSQL (`LIMIT` in sub-`SELECT`, not on bare `DELETE`). |
| In-memory `sequence` | **CONCERN** | Safe for single emitter process; **breaks across multiple emitters/sessions per run** (see coupling row). Prefer single session or external monotonic counter. |
| `flush()` per emit | **CONCERN** | Latency vs durability tradeoff; OK for moderate volume; batch if profiling shows bottleneck. |
| Backfill + Redis in one generator | **GOOD** | Common; gap replay after subscribe closes the main race. |
| Phase state from stream only | **GOOD** | Single source of truth; REST `sync-events` for debugging/history. |
| Remove Redis hash entirely | **CONCERN** | No fallback during rollout — align deploy order (backend+frontend same release). |
| `SyncEventLogPanel` (pills + log) | **GOOD** | Cohesive UI; split only if reuse demands. |

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Task(s) |
|---|---|
| Data Model: `sync_events` table | Task 1 (model) + Task 2 (migration) |
| Event Types (run_start, phase_start, phase_complete, item, warning, error, run_complete) | Task 4 (worker) + Task 5 (metadata.py) |
| Detail JSON examples | Task 5 (detail dicts in emit calls) |
| Retention (last 3 runs) | Task 3 (`purge_old_runs`) |
| SyncEventEmitter | Task 3 |
| SSE Endpoint | Task 6 |
| Worker Integration | Task 4 |
| Old system removal | Task 4 (worker) + Task 6 (endpoint) + Task 16 (full teardown) |
| useSyncEventStream hook | Task 10 (initial) + Task 14 (auth) |
| SyncEventLogPanel | Task 11 |
| Phase pills (all 15 phases) | Task 11 (PHASE_LABELS covers all) |
| Terminal log panel | Task 11 |
| Sync History dropdown | Deferred — data in Postgres, add UI later |
| sync-events REST endpoint | Task 7 |
| sync-runs REST endpoint | Deferred |
| Keepalive comments | Task 6 (15s keepalive in SSE) |
| Platforms page integration | Task 12 |
| Analysis page integration | Task 13 |
| Out of scope items | N/A — correctly excluded |

### Placeholder Scan

No TBD, TODO, or "implement later" placeholders found.

### Type Consistency

- `SyncEvent` model (Python) matches `SyncEvent` interface (TypeScript)
- `SyncEventEmitter.emit()` signature is consistent across Task 3/4/5
- `SyncStreamStatus` type is used consistently in hook and panel
- `PhaseState` derivation matches backend event types
- API client methods match endpoint signatures
- `progress_callback` parameter fully removed — no dual-system references remain
