# Prompt Store & DSPy Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all LLM prompts from hardcoded Python strings into a database-backed prompt store with block-based composition, copy-on-write per-org overrides, and a Settings UI for management.

**Architecture:** New `prompt_block` and `prompt_optimization_run` SQLAlchemy models. A `BLOCK_REGISTRY` defines block types per operation. `resolve_prompt_blocks()` fetches and caches merged blocks at runtime. All existing prompt-building functions refactored to read from the store. Frontend adds a "Prompts" section to the Organization page with block card editors.

**Tech Stack:** SQLAlchemy + Alembic (backend models/migration), FastAPI (API routes), React + React Query + TailwindCSS (frontend UI), DSPy (Phase 1 optimization pipeline — deferred to Task 9)

**Spec:** `docs/superpowers/specs/2026-04-18-prompt-store-design.md`

---

### Task 1: SQLAlchemy Models

**Files:**
- Create: `backend/app/models/prompt.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the PromptBlock model**

Create `backend/app/models/prompt.py`:

```python
"""Prompt Store models — block-based prompt management with copy-on-write overrides."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

if TYPE_CHECKING:
    pass


class PromptBlock(Base):
    __tablename__ = "prompt_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id = Column(String(64), nullable=False, index=True)
    block_type = Column(String(64), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="active")
    forked_from_id = Column(UUID(as_uuid=True), ForeignKey("prompt_blocks.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("operation_id", "block_type", "org_id", "status", name="uq_prompt_block_active"),
    )


class PromptOptimizationRun(Base):
    __tablename__ = "prompt_optimization_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id = Column(String(64), nullable=False)
    block_type = Column(String(64), nullable=False)
    optimizer = Column(String(32), nullable=False)
    metric_name = Column(String(128), nullable=False)
    metric_score_before = Column(Integer, nullable=True)
    metric_score_after = Column(Integer, nullable=True)
    result_block_id = Column(UUID(as_uuid=True), ForeignKey("prompt_blocks.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="running")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Export from models/__init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.prompt import PromptBlock, PromptOptimizationRun
```

And add `"PromptBlock"` and `"PromptOptimizationRun"` to `__all__`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/prompt.py backend/app/models/__init__.py
git commit -m "feat(prompt-store): add PromptBlock and PromptOptimizationRun models"
```

---

### Task 2: Block Registry & Resolution Logic

**Files:**
- Create: `backend/app/services/prompts/registry.py`
- Create: `backend/app/services/prompts/resolver.py`
- Create: `backend/app/services/prompts/__init__.py`

- [ ] **Step 1: Create the block registry**

Create `backend/app/services/prompts/__init__.py` (empty).

Create `backend/app/services/prompts/registry.py`:

```python
"""Block registry — defines which prompt blocks exist per operation and their editability."""
from __future__ import annotations

BLOCK_REGISTRY: dict[str, list[dict]] = {
    "chat": [
        {"type": "identity", "label": "Agent Identity & Role", "editable": True, "required_vars": ["agent_name"], "order": 1},
        {"type": "rules", "label": "Communication Rules", "editable": True, "required_vars": [], "order": 2},
        {"type": "protocol", "label": "Output Protocol", "editable": False, "required_vars": [], "order": 3},
        {"type": "workflow", "label": "Workflow Steps", "editable": True, "required_vars": [], "order": 4},
        {"type": "examples", "label": "Few-Shot Examples", "editable": True, "required_vars": ["agent_name"], "order": 5},
    ],
    "discovery_domain": [
        {"type": "instructions", "label": "Analysis Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_decomposition": [
        {"type": "instructions", "label": "Decomposition Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 2},
    ],
    "discovery_synthesis": [
        {"type": "instructions", "label": "Synthesis Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 2},
    ],
    "metadata_enrichment": [
        {"type": "instructions", "label": "Enrichment Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 2},
    ],
    "entity_extraction": [
        {"type": "instructions", "label": "Single Extraction Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "instructions_batch", "label": "Batch Extraction Instructions", "editable": True, "required_vars": [], "order": 2},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 3},
    ],
    "process_matching": [
        {"type": "instructions", "label": "Matching Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 2},
    ],
    "recommendations": [
        {"type": "instructions", "label": "Document Generation Instructions", "editable": True, "required_vars": [], "order": 1},
        {"type": "protocol", "label": "Output Schema", "editable": False, "required_vars": [], "order": 2},
    ],
}


def get_registry_for_operation(operation_id: str) -> list[dict] | None:
    return BLOCK_REGISTRY.get(operation_id)


def get_block_meta(operation_id: str, block_type: str) -> dict | None:
    blocks = BLOCK_REGISTRY.get(operation_id)
    if not blocks:
        return None
    for b in blocks:
        if b["type"] == block_type:
            return b
    return None


def is_block_editable(operation_id: str, block_type: str) -> bool:
    meta = get_block_meta(operation_id, block_type)
    return meta["editable"] if meta else False


def get_required_vars(operation_id: str, block_type: str) -> list[str]:
    meta = get_block_meta(operation_id, block_type)
    return meta.get("required_vars", []) if meta else []
```

- [ ] **Step 2: Create the resolver**

Create `backend/app/services/prompts/resolver.py`:

```python
"""Prompt resolution — fetches and merges system defaults with org overrides."""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from time import time
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import PromptBlock
from app.services.prompts.registry import BLOCK_REGISTRY

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, str | None], tuple[float, dict[str, str]]] = {}
_CACHE_TTL = 60.0


def _invalidate_cache(operation_id: str, org_id: UUID | None) -> None:
    key = (operation_id, str(org_id) if org_id else None)
    _cache.pop(key, None)
    system_key = (operation_id, None)
    _cache.pop(system_key, None)


async def resolve_prompt_blocks(
    operation_id: str,
    org_id: UUID | None,
    db: AsyncSession,
) -> dict[str, str]:
    """Return merged {block_type: content} for an operation, with org overrides winning."""
    cache_key = (operation_id, str(org_id) if org_id else None)
    now = time()
    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    registry_blocks = BLOCK_REGISTRY.get(operation_id)
    if not registry_blocks:
        return {}

    system_q = select(PromptBlock).where(
        and_(
            PromptBlock.operation_id == operation_id,
            PromptBlock.org_id.is_(None),
            PromptBlock.status == "active",
        )
    )
    system_rows = (await db.execute(system_q)).scalars().all()
    system_map = {r.block_type: r.content for r in system_rows}

    org_map: dict[str, str] = {}
    if org_id is not None:
        org_q = select(PromptBlock).where(
            and_(
                PromptBlock.operation_id == operation_id,
                PromptBlock.org_id == org_id,
                PromptBlock.status == "active",
            )
        )
        org_rows = (await db.execute(org_q)).scalars().all()
        org_map = {r.block_type: r.content for r in org_rows}

    merged: dict[str, str] = {}
    for block_def in sorted(registry_blocks, key=lambda b: b["order"]):
        bt = block_def["type"]
        merged[bt] = org_map.get(bt) or system_map.get(bt, "")

    _cache[cache_key] = (now, merged)
    return merged


async def resolve_prompt_blocks_with_meta(
    operation_id: str,
    org_id: UUID | None,
    db: AsyncSession,
) -> list[dict]:
    """Return blocks with metadata for the API/UI (is_customized, is_locked, etc.)."""
    registry_blocks = BLOCK_REGISTRY.get(operation_id)
    if not registry_blocks:
        return []

    system_q = select(PromptBlock).where(
        and_(
            PromptBlock.operation_id == operation_id,
            PromptBlock.org_id.is_(None),
            PromptBlock.status == "active",
        )
    )
    system_rows = (await db.execute(system_q)).scalars().all()
    system_map = {r.block_type: r for r in system_rows}

    org_map: dict[str, PromptBlock] = {}
    if org_id is not None:
        org_q = select(PromptBlock).where(
            and_(
                PromptBlock.operation_id == operation_id,
                PromptBlock.org_id == org_id,
                PromptBlock.status == "active",
            )
        )
        org_rows = (await db.execute(org_q)).scalars().all()
        org_map = {r.block_type: r for r in org_rows}

    result = []
    for block_def in sorted(registry_blocks, key=lambda b: b["order"]):
        bt = block_def["type"]
        org_block = org_map.get(bt)
        sys_block = system_map.get(bt)
        active = org_block or sys_block
        result.append({
            "block_type": bt,
            "label": block_def["label"],
            "editable": block_def["editable"],
            "content": active.content if active else "",
            "is_customized": org_block is not None,
            "is_locked": not block_def["editable"],
            "available_vars": block_def.get("required_vars", []),
            "version": active.version if active else 0,
        })
    return result


def validate_required_vars(content: str, operation_id: str, block_type: str) -> list[str]:
    """Return list of missing required variables."""
    from app.services.prompts.registry import get_required_vars

    required = get_required_vars(operation_id, block_type)
    missing = []
    for var in required:
        pattern = r"\{" + re.escape(var) + r"\}"
        if not re.search(pattern, content):
            missing.append(var)
    return missing
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/prompts/
git commit -m "feat(prompt-store): add block registry and resolution logic"
```

---

### Task 3: Alembic Migration with Seeding

**Files:**
- Create: `backend/alembic/versions/010_prompt_store.py`
- Create: `backend/app/services/prompts/seeds.py`

- [ ] **Step 1: Create seed data module**

Create `backend/app/services/prompts/seeds.py`. This file contains the exact current prompt text decomposed into blocks. Each entry is `(operation_id, block_type, content)`.

The content for each block is extracted from the current hardcoded prompts explored in the context-gathering phase. The file should contain a `SEED_BLOCKS` list of dicts with `operation_id`, `block_type`, and `content` keys. Each content string is the literal text from the current prompt source files, separated by block boundary.

This file will be long (~300 lines) because it contains the full prompt text for all 8 operations. Each prompt is split at the natural boundaries identified during exploration:
- Chat: identity (layer1), rules (extracted from layer1), protocol (layer2), workflow (layer3), examples (few_shot)
- Discovery passes 1-3: instructions (role + instruction bullets), protocol (JSON schema)
- Describe: instructions (task description), protocol (JSON schema)
- Extraction: instructions (single), instructions_batch (batch), protocol (JSON array/object schema)
- Matching: instructions (task + confidence rule), protocol (JSON array format)
- Recommendations: instructions (task sentence), protocol (JSON object schema)

- [ ] **Step 2: Create the Alembic migration**

Create `backend/alembic/versions/010_prompt_store.py`:

```python
"""Prompt store tables and seed data.

Revision ID: 010
Revises: 009
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_blocks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", sa.String(64), nullable=False, index=True),
        sa.Column("block_type", sa.String(64), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("forked_from_id", UUID(as_uuid=True), sa.ForeignKey("prompt_blocks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("operation_id", "block_type", "org_id", "status", name="uq_prompt_block_active"),
    )

    op.create_table(
        "prompt_optimization_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("block_type", sa.String(64), nullable=False),
        sa.Column("optimizer", sa.String(32), nullable=False),
        sa.Column("metric_name", sa.String(128), nullable=False),
        sa.Column("metric_score_before", sa.Float, nullable=True),
        sa.Column("metric_score_after", sa.Float, nullable=True),
        sa.Column("result_block_id", UUID(as_uuid=True), sa.ForeignKey("prompt_blocks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Seed system defaults from seeds.py
    from app.services.prompts.seeds import SEED_BLOCKS

    prompt_blocks = sa.table(
        "prompt_blocks",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("operation_id", sa.String),
        sa.column("block_type", sa.String),
        sa.column("org_id", UUID(as_uuid=True)),
        sa.column("content", sa.Text),
        sa.column("version", sa.Integer),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    now = datetime.now(timezone.utc)
    rows = []
    for seed in SEED_BLOCKS:
        rows.append({
            "id": uuid.uuid4(),
            "operation_id": seed["operation_id"],
            "block_type": seed["block_type"],
            "org_id": None,
            "content": seed["content"],
            "version": 1,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })

    if rows:
        op.bulk_insert(prompt_blocks, rows)


def downgrade() -> None:
    op.drop_table("prompt_optimization_runs")
    op.drop_table("prompt_blocks")
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/010_prompt_store.py backend/app/services/prompts/seeds.py
git commit -m "feat(prompt-store): migration 010 with tables and seed data"
```

---

### Task 4: API Endpoints

**Files:**
- Create: `backend/app/api/routes/prompts.py`
- Create: `backend/app/schemas/prompt.py`
- Modify: `backend/app/api/router.py` (or wherever routes are registered)

- [ ] **Step 1: Create Pydantic schemas**

Create `backend/app/schemas/prompt.py`:

```python
"""Pydantic schemas for prompt store API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PromptBlockOut(BaseModel):
    block_type: str
    label: str
    editable: bool
    content: str
    is_customized: bool
    is_locked: bool
    available_vars: list[str]
    version: int

    model_config = {"from_attributes": True}


class PromptBlockUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)


class OperationOut(BaseModel):
    operation_id: str
    label: str
    group: str
    blocks: list[dict]


class OperationsListOut(BaseModel):
    operations: list[OperationOut]
```

- [ ] **Step 2: Create API routes**

Create `backend/app/api/routes/prompts.py`:

```python
"""API routes for prompt store management."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, select

from app.api.deps import CurrentOrg, DbSession
from app.models.prompt import PromptBlock
from app.schemas.prompt import (
    OperationsListOut,
    OperationOut,
    PromptBlockOut,
    PromptBlockUpdate,
)
from app.services.ai.operations import MODEL_OPERATIONS, OPERATION_GROUPS
from app.services.prompts.registry import BLOCK_REGISTRY, get_block_meta, is_block_editable
from app.services.prompts.resolver import (
    _invalidate_cache,
    resolve_prompt_blocks_with_meta,
    validate_required_vars,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/operations", response_model=OperationsListOut)
async def list_operations():
    ops = []
    for op_id, blocks in BLOCK_REGISTRY.items():
        op_meta = MODEL_OPERATIONS.get(op_id, {})
        ops.append(OperationOut(
            operation_id=op_id,
            label=op_meta.get("label", op_id),
            group=op_meta.get("group", "other"),
            blocks=[{"type": b["type"], "label": b["label"], "editable": b["editable"]} for b in blocks],
        ))
    return OperationsListOut(operations=ops)


@router.get("/{operation_id}", response_model=list[PromptBlockOut])
async def get_operation_blocks(
    operation_id: str,
    db: DbSession,
    org: CurrentOrg,
):
    if operation_id not in BLOCK_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Operation '{operation_id}' not found")
    blocks = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
    return blocks


@router.put("/{operation_id}/blocks/{block_type}", response_model=PromptBlockOut)
async def update_block(
    operation_id: str,
    block_type: str,
    body: PromptBlockUpdate,
    db: DbSession,
    org: CurrentOrg,
):
    meta = get_block_meta(operation_id, block_type)
    if meta is None:
        raise HTTPException(status_code=404, detail="Block not found")
    if not meta["editable"]:
        raise HTTPException(status_code=403, detail="This block is locked and cannot be customized")

    missing = validate_required_vars(body.content, operation_id, block_type)
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required variables: {', '.join(missing)}")

    # Check if content is identical to system default
    sys_q = select(PromptBlock).where(
        and_(
            PromptBlock.operation_id == operation_id,
            PromptBlock.block_type == block_type,
            PromptBlock.org_id.is_(None),
            PromptBlock.status == "active",
        )
    )
    sys_block = (await db.execute(sys_q)).scalar_one_or_none()
    if sys_block and body.content.strip() == sys_block.content.strip():
        _invalidate_cache(operation_id, org.id)
        blocks = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
        for b in blocks:
            if b["block_type"] == block_type:
                return b
        raise HTTPException(status_code=500, detail="Block resolution failed")

    # Archive existing org override if any
    existing_q = select(PromptBlock).where(
        and_(
            PromptBlock.operation_id == operation_id,
            PromptBlock.block_type == block_type,
            PromptBlock.org_id == org.id,
            PromptBlock.status == "active",
        )
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    next_version = 1
    if existing:
        next_version = existing.version + 1
        existing.status = "archived"
        db.add(existing)

    new_block = PromptBlock(
        operation_id=operation_id,
        block_type=block_type,
        org_id=org.id,
        content=body.content,
        version=next_version,
        status="active",
        forked_from_id=sys_block.id if sys_block else None,
    )
    db.add(new_block)
    await db.commit()

    _invalidate_cache(operation_id, org.id)
    blocks = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
    for b in blocks:
        if b["block_type"] == block_type:
            return b
    raise HTTPException(status_code=500, detail="Block resolution failed")


@router.delete("/{operation_id}/blocks/{block_type}", response_model=PromptBlockOut)
async def restore_block_default(
    operation_id: str,
    block_type: str,
    db: DbSession,
    org: CurrentOrg,
):
    meta = get_block_meta(operation_id, block_type)
    if meta is None:
        raise HTTPException(status_code=404, detail="Block not found")

    existing_q = select(PromptBlock).where(
        and_(
            PromptBlock.operation_id == operation_id,
            PromptBlock.block_type == block_type,
            PromptBlock.org_id == org.id,
            PromptBlock.status == "active",
        )
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    if existing:
        existing.status = "archived"
        db.add(existing)
        await db.commit()

    _invalidate_cache(operation_id, org.id)
    blocks = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
    for b in blocks:
        if b["block_type"] == block_type:
            return b
    raise HTTPException(status_code=500, detail="Block resolution failed")
```

- [ ] **Step 3: Register the router**

In the main API router file (likely `backend/app/api/router.py` or `backend/app/main.py`), add:

```python
from app.api.routes.prompts import router as prompts_router
# ... in the router includes:
app.include_router(prompts_router, prefix="/api/v1")
```

Find the existing pattern by checking where `chat` router is registered and follow the same pattern.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/prompt.py backend/app/api/routes/prompts.py
git commit -m "feat(prompt-store): API endpoints for prompt block CRUD"
```

---

### Task 5: Refactor Chat Prompt to Use Store

**Files:**
- Modify: `backend/app/services/chat/context.py`

- [ ] **Step 1: Refactor build_system_prompt to use resolver**

Change `build_system_prompt()` from building hardcoded layers to fetching blocks from the store. The function signature changes to `async` and takes `db` and `org_id` parameters.

The key change: instead of defining `layer1_identity`, `layer2_protocol`, etc. as local strings, call `resolve_prompt_blocks("chat", org.id, db)` to get the block contents. Then interpolate variables (`agent_name`, etc.) and join with `\n\n`, appending the auto-generated tools and org settings blocks at the end.

**Fallback:** If `resolve_prompt_blocks` returns empty (migration didn't run), fall back to the current hardcoded strings and log a warning.

- [ ] **Step 2: Update build_chat_context to pass db to build_system_prompt**

The caller `build_chat_context()` already has `db` and `org`. Update the call from `build_system_prompt(org, tool_names)` to `await build_system_prompt(org, tool_names, db)`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat/context.py
git commit -m "refactor(chat): read prompt blocks from store with hardcoded fallback"
```

---

### Task 6: Refactor Discovery Prompts to Use Store

**Files:**
- Modify: `backend/app/services/processes/prompts.py`

- [ ] **Step 1: Refactor pass1/2/3 prompt builders**

Change each `build_passN_prompt()` to async. Fetch blocks via `resolve_prompt_blocks("discovery_domain", org_id, db)` (or `discovery_decomposition`, `discovery_synthesis`). The `instructions` block replaces the hardcoded instruction text. The `protocol` block replaces the JSON schema text. Dynamic data sections (org_context, metadata_summary, etc.) are still assembled in code and injected between blocks.

Include the same fallback-to-hardcoded pattern as chat.

- [ ] **Step 2: Update callers**

Find where `build_pass1_prompt`, `build_pass2_prompt`, `build_pass3_prompt` are called (likely in `backend/app/services/processes/discovery.py`) and update to `await` the async versions, passing `db` and `org_id`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/processes/prompts.py backend/app/services/processes/discovery.py
git commit -m "refactor(discovery): read prompt blocks from store with hardcoded fallback"
```

---

### Task 7: Refactor Remaining Operations

**Files:**
- Modify: `backend/app/services/connectors/describe.py`
- Modify: `backend/app/services/extraction/llm_extract.py`
- Modify: `backend/app/services/processes/matcher.py`
- Modify: `backend/app/services/recommendations/synthesis.py`

- [ ] **Step 1: Refactor describe.py**

Replace the `DESCRIBE_PROMPT` constant with an async function that fetches `instructions` and `protocol` blocks for `metadata_enrichment` from the store. Fall back to the current hardcoded string if blocks are empty.

- [ ] **Step 2: Refactor llm_extract.py**

Replace `EXTRACTION_PROMPT` and `BATCH_PROMPT` constants with async lookups for `entity_extraction` blocks (`instructions`, `instructions_batch`, `protocol`). Fall back to current constants if empty.

- [ ] **Step 3: Refactor matcher.py**

Replace the inline prompt in `_llm_disambiguate()` with a lookup for `process_matching` blocks (`instructions`, `protocol`). Fall back to current inline string if empty.

- [ ] **Step 4: Refactor synthesis.py**

Replace the inline prompt in `generate_process_document()` with a lookup for `recommendations` blocks (`instructions`, `protocol`). Fall back to current inline string if empty.

- [ ] **Step 5: Update all callers to pass db/org_id**

Each refactored function now needs `db` and `org_id` parameters. Trace back to the callers and update their signatures to pass these through.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/connectors/describe.py backend/app/services/extraction/llm_extract.py backend/app/services/processes/matcher.py backend/app/services/recommendations/synthesis.py
git commit -m "refactor(operations): read all remaining prompt blocks from store"
```

---

### Task 8: Frontend Types, API Client & Hooks

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Add TypeScript types**

Add to `frontend/src/types/index.ts`:

```typescript
export interface PromptBlockInfo {
  type: string
  label: string
  editable: boolean
}

export interface PromptOperation {
  operation_id: string
  label: string
  group: string
  blocks: PromptBlockInfo[]
}

export interface PromptBlock {
  block_type: string
  label: string
  editable: boolean
  content: string
  is_customized: boolean
  is_locked: boolean
  available_vars: string[]
  version: number
}
```

- [ ] **Step 2: Add API client methods**

In `frontend/src/api/client.ts`, add to the API object:

```typescript
prompts: {
  operations: () => request<{ operations: PromptOperation[] }>('/prompts/operations'),
  blocks: (operationId: string) => request<PromptBlock[]>(`/prompts/${operationId}`),
  updateBlock: (operationId: string, blockType: string, content: string) =>
    request<PromptBlock>(`/prompts/${operationId}/blocks/${blockType}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  restoreBlock: (operationId: string, blockType: string) =>
    request<PromptBlock>(`/prompts/${operationId}/blocks/${blockType}`, {
      method: 'DELETE',
    }),
},
```

- [ ] **Step 3: Add React Query hooks**

In `frontend/src/hooks/useApi.ts`, add:

```typescript
export function usePromptOperations() {
  return useQuery({
    queryKey: ['prompts', 'operations'],
    queryFn: () => api.prompts.operations(),
  })
}

export function usePromptBlocks(operationId: string | null) {
  return useQuery({
    queryKey: ['prompts', 'blocks', operationId],
    queryFn: () => api.prompts.blocks(operationId!),
    enabled: !!operationId,
  })
}

export function useUpdatePromptBlock() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ operationId, blockType, content }: { operationId: string; blockType: string; content: string }) =>
      api.prompts.updateBlock(operationId, blockType, content),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['prompts', 'blocks', vars.operationId] })
    },
  })
}

export function useRestorePromptBlock() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ operationId, blockType }: { operationId: string; blockType: string }) =>
      api.prompts.restoreBlock(operationId, blockType),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['prompts', 'blocks', vars.operationId] })
    },
  })
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat(prompt-store): frontend types, API client, and React Query hooks"
```

---

### Task 9: Frontend Prompts UI

**Files:**
- Create: `frontend/src/components/PromptEditor/PromptBlockCard.tsx`
- Create: `frontend/src/components/PromptEditor/PromptsSection.tsx`
- Modify: `frontend/src/pages/Organization/index.tsx`

- [ ] **Step 1: Create PromptBlockCard component**

Create `frontend/src/components/PromptEditor/PromptBlockCard.tsx`:

A card component that renders a single prompt block. Props: `block: PromptBlock`, `operationId: string`, `onSaved: () => void`. Contains:
- Block label as header, with a `Lock` icon (from lucide-react) if locked and an orange `Customized` badge (`text-xs bg-orange-50 text-orange-700 border border-orange-200 rounded-full px-2 py-0.5`) if `is_customized`
- Textarea (`font-mono text-sm`, disabled with `bg-slate-50 text-slate-400` if locked) with the block content as initial `useState` value
- Small muted text below: `Available variables: {agent_name}` (from `block.available_vars`, displayed as inline code spans)
- Save button (right-aligned, `bg-blue-600 text-white`, disabled with `opacity-50` until content differs from `block.content`)
- Restore defaults `RotateCcw` icon (16px, `text-slate-400 hover:text-orange-600`) — only rendered when `is_customized`. Click sets `confirmRestore` state, showing inline "Restore? **Yes** / **No**" in `text-xs text-red-600` matching the existing chat delete confirmation pattern.

**States:**
- **Save in progress:** Save button shows `Loader2` spinner (animate-spin), disabled. On success: brief `Check` icon in green for 2 seconds, then reverts. On 422: red error text below textarea listing missing variables.
- **Restore in progress:** After "Yes", card content fades to system default. Badge disappears.

Uses `useUpdatePromptBlock()` and `useRestorePromptBlock()` hooks.

- [ ] **Step 2: Create PromptsSection component**

Create `frontend/src/components/PromptEditor/PromptsSection.tsx`:

The main prompts management section. Layout: two-column grid (`grid grid-cols-[240px_1fr] gap-6`).

**Left column:** Uses `usePromptOperations()`. Groups operations by `group` field, with group headers matching `OPERATION_GROUPS` labels (Metadata Pipeline, Analysis, Discovery Pipeline, Synthesis, Chat Assistant). Each operation is a clickable row (`px-3 py-2 rounded-lg text-sm cursor-pointer`). Selected state: `bg-blue-50 text-blue-700 font-medium`. Default first operation selected on mount.

**Right column:** Shows `PromptBlockCard` components for the selected operation, fetched via `usePromptBlocks(selectedOperationId)`. Cards stacked with `space-y-4`.

Below the editable block cards, render a collapsible **"System Context"** section:
- Header: `ChevronDown` icon + "System Context" label + info tooltip (`"These sections are added automatically by the platform and cannot be edited."`)
- Collapsed by default. On expand, shows a muted card (`bg-slate-50 border border-slate-200 text-xs font-mono text-slate-500 p-4`) with a static description of what the platform auto-injects for this operation type. For chat: "Available tools, organization settings, conversation anchor context, RAG search results". For discovery: "Organization context, metadata summary, document excerpts". For others: "Operation-specific data context". This is display-only — no live data fetching.

**States:**
- **Loading:** Left column renders immediately (operation names from registry). Right column shows 3 skeleton cards (`animate-pulse bg-slate-100 rounded-xl h-48`).
- **Error:** Inline red banner with `AlertCircle` icon, error message, and "Retry" button that calls `refetch()`.
- **Empty:** Single muted card: "No prompt blocks configured for this operation."

- [ ] **Step 3: Add PromptsSection to OrganizationPage**

In `frontend/src/pages/Organization/index.tsx`, add a new `<section>` after the existing "Model Configuration" section:

```tsx
<section>
  <h2 className="mb-4 text-lg font-semibold text-slate-900">Prompt Management</h2>
  <p className="mb-6 text-sm text-slate-500">
    Customize the prompts used by each AI operation. Locked blocks maintain system integrity.
  </p>
  <PromptsSection />
</section>
```

Import `PromptsSection` from `@/components/PromptEditor/PromptsSection`.

- [ ] **Step 4: Verify TypeScript build**

Run: `npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/PromptEditor/ frontend/src/pages/Organization/index.tsx
git commit -m "feat(prompt-store): Prompts management UI on Organization page"
```

---

### Task 10: DSPy Integration (Phase 1 — CLI Task)

**Files:**
- Create: `backend/app/services/prompts/optimize.py`
- Modify: `backend/requirements.txt` (add `dspy-ai`)

- [ ] **Step 1: Add DSPy dependency**

Add `dspy-ai>=2.6.0,<3.0.0` to `backend/requirements.txt`.

- [ ] **Step 2: Create optimization task**

Create `backend/app/services/prompts/optimize.py`:

A Celery task `run_prompt_optimization(operation_id, block_type, optimizer_name, metric_name)` that:
1. Fetches the current active system default block content
2. Extracts training examples from Langfuse traces for the operation
3. Defines a DSPy signature matching the operation's input/output
4. Runs the specified optimizer (MIPROv2 or BootstrapFewShot)
5. Creates a new `PromptBlock` with `status="draft"` containing the optimized content
6. Creates a `PromptOptimizationRun` record tracking the job

This task is intentionally a skeleton in v1 — the DSPy signature and metric definitions will need tuning per operation. The infrastructure (task, models, draft creation) is what matters for now.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/prompts/optimize.py backend/requirements.txt
git commit -m "feat(prompt-store): DSPy optimization task skeleton (Phase 1)"
```

---

### Task 11: Final Integration & Push

**Files:**
- All modified files from previous tasks

- [ ] **Step 1: Verify Python imports**

Run: `py -3 -c "from app.models.prompt import PromptBlock, PromptOptimizationRun; from app.services.prompts.registry import BLOCK_REGISTRY; from app.services.prompts.resolver import resolve_prompt_blocks; print('OK')"`
Expected: OK

- [ ] **Step 2: Verify TypeScript build**

Run: `npx tsc --noEmit` in frontend/
Expected: No errors

- [ ] **Step 3: Verify Alembic migration generates correctly**

Run: `alembic upgrade head` (or verify locally if possible)

- [ ] **Step 4: Push to master**

```bash
git push origin master
```
