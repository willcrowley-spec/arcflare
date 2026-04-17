# Platform vs. Organization Information Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the platform to separate platform-specific metadata views from organization-level aggregate intelligence, adding object classification, velocity scoring, and vectorization gating.

**Architecture:** New `/platforms/:connectionId` detail page receives all platform-specific content (metadata catalog, licensing, adoption, roles). Organization page becomes a company intelligence card with inline-editable profile and analysis settings. Analysis page retains only connection management. Backend adds classification/velocity columns, a reanalyze endpoint, and org-level configuration.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic (Postgres), Celery + Redis, React 18, TypeScript, TailwindCSS v4, React Query, React Router, Zustand

**Spec:** `docs/superpowers/specs/2026-04-16-platform-org-information-architecture-design.md`

---

## File Map

### Backend — Create
- `backend/alembic/versions/006_classification_velocity_analysis_config.py` — migration
- `backend/app/services/classification.py` — classification + velocity computation + reanalyze logic
- `backend/app/schemas/settings.py` — analysis config Pydantic schemas

### Backend — Modify
- `backend/app/models/metadata.py` — add columns, drop columns on MetadataObject
- `backend/app/models/organization.py` — add `analysis_config` column
- `backend/app/schemas/metadata.py` — update MetadataObjectResponse, MetadataSummary
- `backend/app/services/sync_progress.py` — update PHASES
- `backend/app/services/salesforce/metadata.py` — remove reports, call classification after sync
- `backend/app/services/metadata_vectorizer.py` — skip empty/deprecated objects, remove report/dashboard vectorization
- `backend/app/workers/metadata_sync.py` — call classification after sync, before vectorization
- `backend/app/api/routes/metadata.py` — add PATCH classification, update object list to include automation_count
- `backend/app/api/routes/organization.py` — add GET/PATCH settings, POST reanalyze
- `backend/app/main.py` — no changes needed (routes already mounted)

### Frontend — Create
- `frontend/src/pages/Platforms/index.tsx` — platform detail page
- `frontend/src/pages/Platforms/DataObjectsTable.tsx` — data objects table with classification editing
- `frontend/src/pages/Platforms/SummaryCards.tsx` — KPI cards for automations, code, etc.

### Frontend — Modify
- `frontend/src/types/index.ts` — update MetadataObject, add Organization settings types
- `frontend/src/api/client.ts` — add new API methods
- `frontend/src/hooks/useApi.ts` — add new hooks
- `frontend/src/App.tsx` — add platform detail route
- `frontend/src/pages/Analysis/index.tsx` — remove catalog, keep connections
- `frontend/src/pages/Organization/index.tsx` — redesign as company card
- `frontend/src/components/SyncProgressPanel.tsx` — update phase labels
- `frontend/src/components/AppLayout.tsx` — make connection cards clickable to platform detail

---

### Task 1: Alembic Migration — Add classification, velocity, analysis_config; drop old columns

**Files:**
- Create: `backend/alembic/versions/006_classification_velocity_analysis_config.py`

- [ ] **Step 1: Create the migration file**

```python
"""Add classification, velocity_score to metadata_objects; analysis_config to organizations; drop deprecated columns."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

DEFAULT_ANALYSIS_CONFIG = {
    "velocity_window_days": 30,
    "classification_threshold": 0.1,
    "min_records_for_vectorization": 1,
    "embedding_provider": "default",
    "vector_store_provider": "default",
    "llm_provider": "default",
}


def upgrade() -> None:
    op.add_column(
        "metadata_objects",
        sa.Column("classification", sa.String(20), nullable=True),
    )
    op.add_column(
        "metadata_objects",
        sa.Column("classification_source", sa.String(10), nullable=False, server_default="auto"),
    )
    op.add_column(
        "metadata_objects",
        sa.Column("velocity_score", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.create_index("ix_metadata_objects_classification", "metadata_objects", ["classification"])

    op.drop_column("metadata_objects", "has_triggers")
    op.drop_column("metadata_objects", "has_flows")
    op.drop_column("metadata_objects", "has_validation_rules")
    op.drop_column("metadata_objects", "last_synced_at")

    op.add_column(
        "organizations",
        sa.Column(
            "analysis_config",
            JSONB(),
            nullable=False,
            server_default=sa.text(f"'{__import__('json').dumps(DEFAULT_ANALYSIS_CONFIG)}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "analysis_config")
    op.drop_index("ix_metadata_objects_classification", table_name="metadata_objects")
    op.drop_column("metadata_objects", "velocity_score")
    op.drop_column("metadata_objects", "classification_source")
    op.drop_column("metadata_objects", "classification")
    op.add_column("metadata_objects", sa.Column("has_triggers", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("metadata_objects", sa.Column("has_flows", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("metadata_objects", sa.Column("has_validation_rules", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("metadata_objects", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
```

- [ ] **Step 2: Run the migration**

```bash
cd backend
alembic upgrade head
```

Expected: Migration completes successfully. Tables updated.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/006_classification_velocity_analysis_config.py
git commit -m "feat: migration 006 — classification, velocity, analysis_config"
```

---

### Task 2: Update Backend Models

**Files:**
- Modify: `backend/app/models/metadata.py`
- Modify: `backend/app/models/organization.py`

- [ ] **Step 1: Update MetadataObject model**

In `backend/app/models/metadata.py`, replace the `has_triggers`, `has_flows`, `has_validation_rules`, and `last_synced_at` column definitions with the new classification columns. The model should have these columns after the edit:

```python
class MetadataObject(Base):
    __tablename__ = "metadata_objects"
    __table_args__ = (
        UniqueConstraint("connection_id", "api_name", name="uq_metadata_objects_connection_api_name"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"),
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    field_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    managed_package_namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    classification_source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="auto")
    velocity_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
```

Add `Float` to the sqlalchemy imports at the top of the file.

Remove the `has_triggers`, `has_flows`, `has_validation_rules`, and `last_synced_at` mapped_column definitions entirely.

- [ ] **Step 2: Update Organization model**

In `backend/app/models/organization.py`, add `analysis_config` column to the Organization class, after `settings_json`:

```python
    analysis_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(
            "'{\"velocity_window_days\":30,\"classification_threshold\":0.1,"
            "\"min_records_for_vectorization\":1,\"embedding_provider\":\"default\","
            "\"vector_store_provider\":\"default\",\"llm_provider\":\"default\"}'::jsonb"
        ),
    )
```

Add `JSONB` to the sqlalchemy.dialects.postgresql import if not already there (it is).

- [ ] **Step 3: Verify models compile**

```bash
cd backend
python -c "from app.models.metadata import MetadataObject; from app.models.organization import Organization; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/metadata.py backend/app/models/organization.py
git commit -m "feat: update MetadataObject + Organization models for classification & config"
```

---

### Task 3: Backend Schemas — MetadataObjectResponse, Settings

**Files:**
- Modify: `backend/app/schemas/metadata.py`
- Create: `backend/app/schemas/settings.py`

- [ ] **Step 1: Update MetadataObjectResponse**

Replace the full `MetadataObjectResponse` class in `backend/app/schemas/metadata.py`:

```python
class MetadataObjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    connection_id: UUID
    api_name: str
    label: str | None
    object_type: str | None
    field_count: int
    record_count: int
    is_custom: bool
    managed_package_namespace: str | None
    classification: str | None
    classification_source: str
    velocity_score: float
    automation_count: int = 0
    metadata_json: dict
```

- [ ] **Step 2: Create settings schemas**

Create `backend/app/schemas/settings.py`:

```python
from pydantic import BaseModel, Field


class AnalysisConfig(BaseModel):
    velocity_window_days: int = Field(default=30, ge=1, le=730)
    classification_threshold: float = Field(default=0.1, ge=0.0)
    min_records_for_vectorization: int = Field(default=1, ge=0)
    embedding_provider: str = "default"
    vector_store_provider: str = "default"
    llm_provider: str = "default"


class AnalysisConfigUpdate(BaseModel):
    velocity_window_days: int | None = Field(default=None, ge=1, le=730)
    classification_threshold: float | None = Field(default=None, ge=0.0)
    min_records_for_vectorization: int | None = Field(default=None, ge=0)


class ClassificationUpdate(BaseModel):
    classification: str = Field(..., pattern="^(operational|configuration|empty|deprecated)$")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/metadata.py backend/app/schemas/settings.py
git commit -m "feat: update metadata response schema, add settings schemas"
```

---

### Task 4: Classification & Velocity Service

**Files:**
- Create: `backend/app/services/classification.py`

- [ ] **Step 1: Create the classification service**

```python
"""Object classification and velocity scoring."""
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataObject, RecordTelemetry
from app.models.organization import Organization

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "velocity_window_days": 30,
    "classification_threshold": 0.1,
    "min_records_for_vectorization": 1,
}


def _get_config(org: Organization) -> dict:
    config = org.analysis_config or {}
    return {**DEFAULT_CONFIG, **config}


async def compute_velocity_for_object(
    object_id: UUID,
    window_days: int,
    db: AsyncSession,
) -> float:
    since = datetime.now(tz=UTC) - timedelta(days=window_days)
    q = await db.execute(
        select(
            func.coalesce(func.sum(RecordTelemetry.created_count_delta), 0),
            func.coalesce(func.sum(RecordTelemetry.modified_count_delta), 0),
        ).where(
            RecordTelemetry.object_id == object_id,
            RecordTelemetry.snapshot_at >= since,
        )
    )
    created_sum, modified_sum = q.one()
    return float((created_sum or 0) + (modified_sum or 0))


def classify_object(record_count: int, velocity_score: float, threshold: float) -> str:
    if record_count == 0:
        return "empty"
    if velocity_score > threshold:
        return "operational"
    return "configuration"


async def run_classification(
    org_id: UUID,
    db: AsyncSession,
    connection_id: UUID | None = None,
) -> int:
    """Compute velocity and classification for all auto-classified objects in an org."""
    org = await db.get(Organization, org_id)
    if org is None:
        return 0
    config = _get_config(org)
    window = config["velocity_window_days"]
    threshold = config["classification_threshold"]

    filters = [
        MetadataObject.org_id == org_id,
        MetadataObject.classification_source != "manual",
    ]
    if connection_id:
        filters.append(MetadataObject.connection_id == connection_id)

    result = await db.execute(select(MetadataObject).where(*filters))
    objects = result.scalars().all()

    count = 0
    for obj in objects:
        velocity = await compute_velocity_for_object(obj.id, window, db)
        obj.velocity_score = velocity
        obj.classification = classify_object(obj.record_count, velocity, threshold)
        count += 1

    await db.flush()
    logger.info("classification_complete org=%s objects=%d", org_id, count)
    return count


async def reanalyze_org(org_id: UUID, db: AsyncSession) -> int:
    """Re-run classification using current config. Does NOT re-sync or re-vectorize."""
    count = await run_classification(org_id, db)
    await db.commit()
    return count
```

- [ ] **Step 2: Verify it compiles**

```bash
cd backend
python -c "from app.services.classification import run_classification, reanalyze_org; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/classification.py
git commit -m "feat: classification & velocity service"
```

---

### Task 5: Update Sync Pipeline — Phases, Reports Removal, Classification Call

**Files:**
- Modify: `backend/app/services/sync_progress.py`
- Modify: `backend/app/workers/metadata_sync.py`
- Modify: `backend/app/services/metadata_vectorizer.py`

- [ ] **Step 1: Update PHASES in sync_progress.py**

Replace the `PHASES` list in `backend/app/services/sync_progress.py`:

```python
PHASES = [
    "objects",
    "automations",
    "code",
    "permissions",
    "ui_components",
    "installed_packages",
    "licensing",
    "user_velocity",
    "entities",
    "classification",
    "vectorization",
]
```

- [ ] **Step 2: Update metadata_sync worker to call classification**

Replace `backend/app/workers/metadata_sync.py` entirely:

```python
import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.connection import PlatformConnection
    from app.services.classification import run_classification
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

    async def _run_sync() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn:
                conn.status = "syncing"
                await session.commit()
            return await sync_metadata(UUID(connection_id), session, progress_callback=progress_cb)

    async def _run_classification() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn is None:
                return 0
            count = await run_classification(conn.org_id, session, connection_id=UUID(connection_id))
            await session.commit()
            return count

    async def _run_vectorize() -> int:
        from app.services.metadata_vectorizer import vectorize_org_metadata

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn is None:
                return 0
            return await vectorize_org_metadata(UUID(connection_id), conn.org_id, session)

    async def _mark_connected() -> None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn:
                conn.status = "connected"
                await session.commit()

    try:
        asyncio.run(_run_sync())

        update_phase(connection_id, "classification", "pulling", 0, r)
        try:
            count = asyncio.run(_run_classification())
            update_phase(connection_id, "classification", "done", count, r)
        except Exception as ce:
            logger.warning("classification_failed connection=%s error=%s", connection_id, ce)
            update_phase(connection_id, "classification", "done", 0, r)

        update_phase(connection_id, "vectorization", "pulling", 0, r)
        try:
            count = asyncio.run(_run_vectorize())
            update_phase(connection_id, "vectorization", "done", count, r)
        except Exception as ve:
            logger.warning("vectorization_failed connection=%s error=%s", connection_id, ve)
            update_phase(connection_id, "vectorization", "done", 0, r)

        complete_progress(connection_id, r=r)
    except Exception as exc:
        complete_progress(connection_id, error=str(exc), r=r)
        raise

    asyncio.run(_mark_connected())
    return connection_id
```

- [ ] **Step 3: Update vectorizer to skip empty/deprecated objects**

In `backend/app/services/metadata_vectorizer.py`, modify the objects query in `vectorize_org_metadata` (around line 204) to filter out empty and deprecated objects:

Replace:
```python
    objects = (
        await db.execute(
            select(MetadataObject).where(MetadataObject.connection_id == connection_id)
        )
    ).scalars().all()
```

With:
```python
    objects = (
        await db.execute(
            select(MetadataObject).where(
                MetadataObject.connection_id == connection_id,
                MetadataObject.record_count > 0,
                sa.or_(
                    MetadataObject.classification.is_(None),
                    MetadataObject.classification.notin_(["empty", "deprecated"]),
                ),
            )
        )
    ).scalars().all()
```

Add `import sqlalchemy as sa` at the top of the file if not present.

Also update `_describe_object` to use `classification` instead of the old boolean flags. Replace the automation flags block (lines 33–41):

```python
    if obj.classification:
        lines.append(f"Classification: {obj.classification.title()}")
```

Remove the `if obj.has_triggers` / `has_flows` / `has_validation_rules` block entirely.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/sync_progress.py backend/app/workers/metadata_sync.py backend/app/services/metadata_vectorizer.py
git commit -m "feat: sync pipeline — new phases, classification step, vectorization gating"
```

---

### Task 6: Update sync_metadata to Use New Phase Names & Remove Reports

**Files:**
- Modify: `backend/app/services/salesforce/metadata.py`

This file is large (~900 lines). The key changes are:

- [ ] **Step 1: Map old phase callbacks to new names**

In the `sync_metadata` function, find all `progress_callback` calls and update them:

- `progress_callback(cid, "fields", ...)` → merge into `"objects"` (remove separate fields phase reporting)
- `progress_callback(cid, "flows", ...)` → `progress_callback(cid, "automations", ...)`
- `progress_callback(cid, "triggers", ...)` → `progress_callback(cid, "automations", ...)`
- `progress_callback(cid, "validation_rules", ...)` → `progress_callback(cid, "automations", ...)`
- `progress_callback(cid, "apex_classes", ...)` → `progress_callback(cid, "code", ...)`
- `progress_callback(cid, "reports", ...)` → remove entirely

For the automations phase, use a single "pulling" at the start and a single "done" with the combined count at the end.

- [ ] **Step 2: Remove report/dashboard pulling**

Find the section that pulls reports and dashboards (within `pull_all_ui_components` or the reports progress section) and remove it. In the sync_metadata function, remove the `reports` progress_callback calls and any logic that inserts `component_category = "report"` or `component_category = "dashboard"` into `metadata_components`.

- [ ] **Step 3: Remove has_triggers/has_flows/has_validation_rules assignments**

In the sync_metadata function, find where `has_triggers`, `has_flows`, and `has_validation_rules` are set on MetadataObject instances and remove those assignments. They no longer exist on the model.

- [ ] **Step 4: Verify the backend starts**

```bash
cd backend
python -c "from app.services.salesforce.metadata import sync_metadata; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/salesforce/metadata.py
git commit -m "feat: sync_metadata — new phase names, remove reports, drop boolean flags"
```

---

### Task 7: Backend API — Classification, Settings, Reanalyze Endpoints

**Files:**
- Modify: `backend/app/api/routes/metadata.py`
- Modify: `backend/app/api/routes/organization.py`

- [ ] **Step 1: Add PATCH classification endpoint to metadata routes**

In `backend/app/api/routes/metadata.py`, add this endpoint:

```python
from app.schemas.settings import ClassificationUpdate

@router.patch("/objects/{object_id}/classification")
async def update_classification(
    object_id: UUID,
    body: ClassificationUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> MetadataObjectResponse:
    from app.models.metadata import MetadataObject

    obj = await db.get(MetadataObject, object_id)
    if obj is None or obj.org_id != org.id:
        raise HTTPException(status_code=404, detail="Object not found")
    obj.classification = body.classification
    obj.classification_source = "manual"
    await db.commit()
    await db.refresh(obj)

    automation_count = await db.scalar(
        select(func.count()).select_from(MetadataAutomation).where(
            MetadataAutomation.related_object == obj.api_name,
            MetadataAutomation.connection_id == obj.connection_id,
        )
    )
    resp = MetadataObjectResponse.model_validate(obj)
    resp.automation_count = int(automation_count or 0)
    return resp
```

Add the necessary imports at the top: `MetadataAutomation` from models, `func` from sqlalchemy.

- [ ] **Step 2: Update the objects list endpoint to include automation_count**

In the existing `list_objects` endpoint, after fetching objects, compute automation counts. This can be done with a subquery or post-query loop. The simplest approach for now:

After the object list query, add a loop that fetches automation counts per object:

```python
    items = []
    for obj in rows:
        auto_count = await db.scalar(
            select(func.count()).select_from(MetadataAutomation).where(
                MetadataAutomation.related_object == obj.api_name,
                MetadataAutomation.connection_id == obj.connection_id,
            )
        )
        resp = MetadataObjectResponse.model_validate(obj)
        resp.automation_count = int(auto_count or 0)
        items.append(resp)
```

- [ ] **Step 3: Add settings and reanalyze endpoints to organization routes**

In `backend/app/api/routes/organization.py`, add:

```python
from app.schemas.settings import AnalysisConfig, AnalysisConfigUpdate

@router.get("/settings", response_model=AnalysisConfig)
async def get_settings(org: CurrentOrg) -> AnalysisConfig:
    config = org.analysis_config or {}
    return AnalysisConfig(**config)


@router.patch("/settings", response_model=AnalysisConfig)
async def update_settings(
    body: AnalysisConfigUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> AnalysisConfig:
    config = dict(org.analysis_config or {})
    for k, v in body.model_dump(exclude_unset=True).items():
        config[k] = v
    org.analysis_config = config
    await db.commit()
    await db.refresh(org)
    return AnalysisConfig(**org.analysis_config)


@router.post("/reanalyze")
async def reanalyze(
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str | int]:
    from app.services.classification import reanalyze_org
    count = await reanalyze_org(org.id, db)
    return {"status": "completed", "objects_reclassified": count}
```

- [ ] **Step 4: Verify endpoints compile**

```bash
cd backend
python -c "from app.api.routes.metadata import router; from app.api.routes.organization import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/metadata.py backend/app/api/routes/organization.py
git commit -m "feat: API — classification PATCH, org settings, reanalyze endpoint"
```

---

### Task 8: Frontend Types & API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Update MetadataObject type**

In `frontend/src/types/index.ts`, replace the `MetadataObject` interface:

```typescript
export interface MetadataObject {
  id: string
  org_id?: string
  connection_id?: string
  api_name: string
  label: string | null
  object_type?: string | null
  field_count: number
  record_count: number
  is_custom: boolean
  managed_package_namespace?: string | null
  classification?: string | null
  classification_source?: string
  velocity_score?: number
  automation_count?: number
  metadata_json?: Record<string, unknown>
  platform?: PlatformType
  type?: EntityType
  status?: RecordStatus
  last_updated_at?: string
  description?: string
}
```

Add the AnalysisConfig type after the Organization interface:

```typescript
export interface AnalysisConfig {
  velocity_window_days: number
  classification_threshold: number
  min_records_for_vectorization: number
  embedding_provider: string
  vector_store_provider: string
  llm_provider: string
}
```

- [ ] **Step 2: Add API methods to client**

In `frontend/src/api/client.ts`, add to the `metadata` section:

```typescript
    updateClassification: (objectId: string, classification: string) =>
      request<MetadataObject>(`/metadata/objects/${objectId}/classification`, {
        method: 'PATCH',
        body: JSON.stringify({ classification }),
      }),
```

Add to the `organization` section:

```typescript
    settings: () => request<AnalysisConfig>('/organization/settings'),
    updateSettings: (data: Partial<AnalysisConfig>) =>
      request<AnalysisConfig>('/organization/settings', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    reanalyze: () => request<{ status: string; objects_reclassified: number }>('/organization/reanalyze', { method: 'POST' }),
```

Add the `AnalysisConfig` import to the imports from `@/types`.

- [ ] **Step 3: Add hooks**

In `frontend/src/hooks/useApi.ts`, add:

```typescript
export function useUpdateClassification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ objectId, classification }: { objectId: string; classification: string }) =>
      api.metadata.updateClassification(objectId, classification),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['metadata'] })
    },
  })
}

export function useOrgSettings() {
  return useQuery({
    queryKey: ['organization', 'settings'],
    queryFn: () => api.organization.settings(),
  })
}

export function useUpdateOrgSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.organization.updateSettings(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['organization', 'settings'] })
    },
  })
}

export function useReanalyze() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.organization.reanalyze(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['metadata'] })
    },
  })
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: Clean compile (0 errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat: frontend types, API client, hooks for classification & settings"
```

---

### Task 9: Frontend — Platform Detail Page

**Files:**
- Create: `frontend/src/pages/Platforms/index.tsx`
- Create: `frontend/src/pages/Platforms/DataObjectsTable.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add route in App.tsx**

In `frontend/src/App.tsx`, add the import and route:

```typescript
import PlatformDetailPage from '@/pages/Platforms'
```

Add inside the `<Route element={<AppLayout />}>` block:

```typescript
<Route path="/platforms/:connectionId" element={<PlatformDetailPage />} />
```

- [ ] **Step 2: Create the DataObjectsTable component**

Create `frontend/src/pages/Platforms/DataObjectsTable.tsx`. This is the core table component with classification editing.

The component should:
- Accept `rows: MetadataObject[]` and `isLoading: boolean` props
- Use the existing `DataTable` component with custom columns: Entity, Type, Classification (editable), Records, Velocity, Automations
- Classification column renders a clickable badge that opens a dropdown to select: Operational, Configuration, Empty, Deprecated
- Empty rows (record_count === 0) render with `opacity-60` styling
- Velocity column shows a colored dot: green for > threshold ("hot"), amber for > 0 ("warm"), gray for 0 ("cold")
- Use `useUpdateClassification` hook for the PATCH call

This is a substantial component (~150–200 lines). Build it with the `DataTable` as the base, adding the classification selector as an inline popover.

- [ ] **Step 3: Create the Platform Detail page**

Create `frontend/src/pages/Platforms/index.tsx`. This page:
- Uses `useParams()` to get `connectionId`
- Fetches connection details via `useConnections()` (find by ID in the list)
- Fetches metadata objects via `useMetadataObjects({ connection_id: connectionId })`
- Fetches metadata summary via `useMetadataSummary()`
- Renders: header with platform info + sync/reauth actions, KPI row, DataObjectsTable, and placeholder sections for Automations Summary, Code Summary, Licensing, Platform Adoption, Role/Profile Distribution, Installed Packages

For the relocated sections (Licensing, Platform Adoption, Role/Profile), reuse the existing hooks (`useOrgLicensing`, `useUserVelocity`, etc.) and render the same data. These sections can initially be simplified card views — the `impeccable` skill `/polish` pass will refine them later.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Platforms/ frontend/src/App.tsx
git commit -m "feat: platform detail page with data objects table + classification editing"
```

---

### Task 10: Frontend — Organization Page Redesign

**Files:**
- Modify: `frontend/src/pages/Organization/index.tsx`

- [ ] **Step 1: Redesign Organization page**

Replace the entire Organization page with the company intelligence card layout. The new page has three sections:

**Company Profile** — inline-editable card with:
- Company Name (text input)
- Domains/Websites (multi-value chip input — type + Enter to add, X to remove)
- Industry (searchable select dropdown)
- Estimated Headcount (number input)
- Estimated Annual Revenue (currency input)
- Key Contacts (repeatable name + role rows)

Each field starts in "read" mode showing the value. Clicking the value or a pencil icon transitions it to edit mode inline. Auto-saves on blur or Enter.

The profile data comes from `useOrgProfile()`. Updates go through a new `PATCH /organization/profile` endpoint (or store in `settings_json` — use what's available). If the backend doesn't have all these fields yet, store them in the existing `settings_json` column on Organization.

**Connected Platforms** — card row from `useConnections()`. Each card shows platform name, status, last sync, click-through to `/platforms/:connectionId`. Aggregate spend total above.

**Analysis Settings** — form with:
- Velocity Window (number input, suffix "days")
- Classification Threshold (number input)
- Min Records for Vectorization (number input)
- "Re-analyze" button using `useReanalyze()` hook

Uses `useOrgSettings()` and `useUpdateOrgSettings()` hooks. Auto-saves on blur.

Remove all current sections: Org Hierarchy, Salesforce Licensing, Platform Adoption, Role & Profile Distribution, User Velocity charts, Business Profile.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Organization/index.tsx
git commit -m "feat: organization page — company intelligence card with analysis settings"
```

---

### Task 11: Frontend — Analysis Page Cleanup

**Files:**
- Modify: `frontend/src/pages/Analysis/index.tsx`

- [ ] **Step 1: Strip the metadata catalog**

This is the biggest frontend edit. The Analysis page currently has ~1140 lines. After cleanup it should be ~200–300 lines.

**Keep:**
- The connection management section (Platform Sources cards)
- The `ConnectPlatformModal` integration
- The `SyncProgressPanel` integration
- The sync/reauth handlers

**Remove:**
- All metadata catalog tabs (Objects, Automations, Apex, Reports, Permissions, Packages)
- The `MetadataSummary` KPI cards at the top
- The type filter state and dropdown
- All `objectColumns`, `automationColumns`, `apexColumns`, `permissionColumns`, `packageColumns` definitions
- The `useAnalysisRows`, `rowKind`, `rowStatus` helper functions
- All the `renderObjectsTable()`, `renderAutomationsTable()`, etc. functions
- The tab switching logic

**Add:**
- Make each connection card clickable — wrap in `<Link to={`/platforms/${conn.id}`}>` or use `onClick` + `navigate()`
- A quality empty state below the connections when no ecosystem analysis is available yet

**Result:** The page shows the Platform Sources section only. Each card is a click-through to the platform detail page.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Analysis/index.tsx
git commit -m "feat: analysis page — strip catalog, keep connection management"
```

---

### Task 12: Frontend — Update Sync Progress Phase Labels

**Files:**
- Modify: `frontend/src/components/SyncProgressPanel.tsx`

- [ ] **Step 1: Update PHASE_LABELS and PHASE_ORDER**

Replace the `PHASE_LABELS` and `PHASE_ORDER` constants:

```typescript
const PHASE_LABELS: Record<string, string> = {
  objects: 'Data Objects',
  automations: 'Automations',
  code: 'Code',
  permissions: 'Permissions',
  ui_components: 'UI Components',
  installed_packages: 'Packages',
  licensing: 'Licensing',
  user_velocity: 'User Velocity',
  entities: 'Org Hierarchy',
  classification: 'Classification',
  vectorization: 'Vectorization',
}

const PHASE_ORDER = Object.keys(PHASE_LABELS)
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SyncProgressPanel.tsx
git commit -m "feat: sync progress panel — updated phase labels"
```

---

### Task 13: Skill Updates — Configurability Heuristic

**Files:**
- Modify: `C:\Users\willi\.cursor\skills\salesforce-development\SKILL.md`
- Modify: `C:\Users\willi\.cursor\skills\react-quality\SKILL.md`

- [ ] **Step 1: Add configurability heuristic to salesforce-development skill**

Append the following section to the end of the skill file:

```markdown
## Configurability Check

When implementing business logic with hardcoded thresholds, timeframes, or constants that affect analysis quality, output fidelity, or could reasonably vary by customer:

1. Flag whether the value should be an org-level configuration variable
2. Check if it belongs in the Organization `analysis_config` JSON column
3. Prefer reading from config over hardcoded constants
4. If adding a new config key, ensure it has a sensible default and validation constraints

Examples: velocity windows, classification thresholds, minimum record counts, scoring weights, API rate limits.
```

- [ ] **Step 2: Add configurability heuristic to react-quality skill**

Append the following section to the end of the skill file:

```markdown
## Configurability Awareness

When building UI that displays or controls analysis parameters:

1. Check if hardcoded display thresholds (e.g., "hot" vs "cold" velocity cutoffs, color breakpoints) should be derived from org-level config
2. When adding new tunable controls, wire them to the `useOrgSettings` / `useUpdateOrgSettings` hooks and the Organization analysis settings section
3. Ensure settings changes provide immediate visual feedback and offer a "Re-analyze" action when the change affects backend computations
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: add configurability heuristic to salesforce-development + react-quality skills"
```

---

### Task 14: Build, Push, Deploy

**Files:** None (deployment task)

- [ ] **Step 1: Full TypeScript compile check**

```bash
cd frontend
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 2: Verify backend starts**

```bash
cd backend
python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Push to remote**

```bash
git push origin master
```

- [ ] **Step 4: Deploy backend + worker**

```bash
cd backend
railway up -c -s arcflare-backend
railway up -c -s arcflare-worker
```

- [ ] **Step 5: Run migration on Railway**

```bash
railway run -s arcflare-backend alembic upgrade head
```

- [ ] **Step 6: Deploy frontend**

```bash
cd frontend
railway up -c -s arcflare-frontend
```

- [ ] **Step 7: Verify deployment**

Confirm the frontend loads, the Analysis page shows connections without the catalog, clicking a connection navigates to `/platforms/:id`, and the Organization page shows the company card.
