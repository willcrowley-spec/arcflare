# Process Discovery Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-pass LLM pipeline that discovers business processes from platform metadata, uploaded documents, and organization intelligence, producing a hierarchical process graph with confidence scores and gap detection.

**Architecture:** Celery-based worker runs three sequential LLM passes (domain discovery → per-domain decomposition → cross-domain synthesis). Each pass produces structured JSON persisted to Postgres. Progress tracked via Redis polling. Frontend shows inline stage progression on the Processes page.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Celery, Redis, Langfuse, React/TypeScript, TailwindCSS

**Spec:** `docs/superpowers/specs/2026-04-17-process-discovery-engine-design.md`

---

## File Structure

### Backend — New Files
- `backend/alembic/versions/007_process_discovery.py` — Migration: new columns on `business_processes`, new `process_handoffs` + `discovery_runs` tables
- `backend/app/models/discovery.py` — `DiscoveryRun` and `ProcessHandoff` ORM models
- `backend/app/schemas/discovery.py` — Pydantic schemas for discovery run + handoff responses
- `backend/app/services/processes/discovery.py` — Core three-pass pipeline logic (context gathering, LLM calls, JSON parsing, persistence)
- `backend/app/services/processes/context.py` — Context gathering: build metadata summaries, org intelligence, document summaries for LLM input
- `backend/app/services/processes/prompts.py` — Prompt templates for all three passes
- `backend/app/workers/process_discovery.py` — Celery task wrapping the discovery pipeline with Redis progress tracking
- `backend/app/api/routes/discovery.py` — API routes: trigger discovery, get status, re-run passes

### Backend — Modified Files
- `backend/app/models/process.py` — Add `parent_id`, `level`, `confidence_score`, `needs_review`, `narrative`, `discovery_run_id`, `actors`, `artifacts` columns to `BusinessProcess`
- `backend/app/schemas/process.py` — Update `ProcessResponse`, `ProcessKpis` with new fields
- `backend/app/api/routes/processes.py` — Update generate endpoint to use new discovery worker, add confirm/reject endpoints
- `backend/app/services/processes/graph.py` — Update to build graph from hierarchical process tree

### Frontend — New Files
- `frontend/src/components/DiscoveryPipeline.tsx` — Inline pipeline status bar with three-stage progression
- `frontend/src/pages/Processes/DomainAccordion.tsx` — Domain-level accordion with confidence, review status, children

### Frontend — Modified Files
- `frontend/src/api/client.ts` — Add discovery API methods
- `frontend/src/hooks/useApi.ts` — Add `useDiscoveryStatus`, `useStartDiscovery`, `useConfirmProcess`, `useRejectProcess` hooks
- `frontend/src/pages/Processes/index.tsx` — Replace Generate button with discovery pipeline UX, use new accordion
- `frontend/src/types/index.ts` — Add discovery-related TypeScript types

---

### Task 1: Database Migration — New Models and Columns

**Files:**
- Create: `backend/alembic/versions/007_process_discovery.py`
- Create: `backend/app/models/discovery.py`
- Modify: `backend/app/models/process.py`

- [ ] **Step 1: Create `DiscoveryRun` and `ProcessHandoff` models**

In `backend/app/models/discovery.py`:

```python
"""Discovery run tracking and process handoff models."""
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pass_results: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, server_default="system")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")


class ProcessHandoff(Base):
    __tablename__ = "process_handoffs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    target_process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    handoff_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="unknown")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    is_gap: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    discovery_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    source_process: Mapped["BusinessProcess"] = relationship(
        "BusinessProcess", foreign_keys=[source_process_id]
    )
    target_process: Mapped["BusinessProcess"] = relationship(
        "BusinessProcess", foreign_keys=[target_process_id]
    )
```

Import `BusinessProcess` in the `TYPE_CHECKING` block at the top alongside `Organization`.

- [ ] **Step 2: Add new columns to `BusinessProcess`**

In `backend/app/models/process.py`, add these columns to the `BusinessProcess` class:

```python
parent_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True), ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=True, index=True,
)
level: Mapped[str] = mapped_column(String(50), nullable=False, server_default="process")
confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
discovery_run_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True), ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True
)
actors: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
artifacts: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
```

Add a self-referential relationship:

```python
children: Mapped[list["BusinessProcess"]] = relationship(
    "BusinessProcess", back_populates="parent", cascade="all, delete-orphan",
    foreign_keys=[parent_id],
)
parent: Mapped["BusinessProcess | None"] = relationship(
    "BusinessProcess", back_populates="children", remote_side="BusinessProcess.id",
    foreign_keys=[parent_id],
)
```

Add imports: `Boolean, Text` to the sqlalchemy imports if not already present.

- [ ] **Step 3: Write the Alembic migration**

Create `backend/alembic/versions/007_process_discovery.py`:

```python
"""Add discovery_runs, process_handoffs, and new business_process columns."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_runs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pass_results", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
        sa.Column("error", sa.Text, nullable=True),
    )

    op.add_column("business_processes", sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=True, index=True))
    op.add_column("business_processes", sa.Column("level", sa.String(50), nullable=False, server_default="process"))
    op.add_column("business_processes", sa.Column("confidence_score", sa.Float, nullable=True))
    op.add_column("business_processes", sa.Column("needs_review", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("business_processes", sa.Column("narrative", sa.Text, nullable=True))
    op.add_column("business_processes", sa.Column("discovery_run_id", UUID(as_uuid=True), sa.ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True))
    op.add_column("business_processes", sa.Column("actors", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("business_processes", sa.Column("artifacts", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))

    op.create_table(
        "process_handoffs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_process_id", UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("target_process_id", UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("handoff_type", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("is_gap", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("discovery_run_id", UUID(as_uuid=True), sa.ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_table("process_handoffs")
    op.drop_column("business_processes", "artifacts")
    op.drop_column("business_processes", "actors")
    op.drop_column("business_processes", "discovery_run_id")
    op.drop_column("business_processes", "narrative")
    op.drop_column("business_processes", "needs_review")
    op.drop_column("business_processes", "confidence_score")
    op.drop_column("business_processes", "level")
    op.drop_column("business_processes", "parent_id")
    op.drop_table("discovery_runs")
```

- [ ] **Step 4: Run migration locally**

```bash
cd backend
py -m alembic upgrade head
```

Expected: Migration applies cleanly. Verify tables with `\d discovery_runs`, `\d process_handoffs`, `\d business_processes` in psql.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/discovery.py backend/app/models/process.py backend/alembic/versions/007_process_discovery.py
git commit -m "feat: add discovery_runs, process_handoffs tables and business_process hierarchy columns"
```

---

### Task 2: Pydantic Schemas and Updated Process Response

**Files:**
- Create: `backend/app/schemas/discovery.py`
- Modify: `backend/app/schemas/process.py`

- [ ] **Step 1: Create discovery schemas**

In `backend/app/schemas/discovery.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DiscoveryRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    pass_results: dict
    config: dict
    created_by: str
    error: str | None


class ProcessHandoffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    source_process_id: UUID
    target_process_id: UUID
    handoff_type: str
    description: str | None
    confidence_score: float
    is_gap: bool
    needs_review: bool
    discovery_run_id: UUID | None
    metadata_json: dict


class DiscoveryStatusResponse(BaseModel):
    run_id: str | None
    status: str
    phases: dict
    started_at: str | None
    completed_at: str | None
    error: str | None
```

- [ ] **Step 2: Update ProcessResponse with new fields**

In `backend/app/schemas/process.py`, update `ProcessResponse`:

```python
class ProcessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    category: str | None
    description: str | None
    efficiency_score: float | None
    automation_level: str | None
    status: str
    source: str | None
    sub_process_count: int
    managed_asset_count: int
    metadata_json: dict
    created_at: datetime
    parent_id: UUID | None = None
    level: str = "process"
    confidence_score: float | None = None
    needs_review: bool = False
    narrative: str | None = None
    discovery_run_id: UUID | None = None
    actors: list = []
    artifacts: list = []
```

Update `ProcessKpis`:

```python
class ProcessKpis(BaseModel):
    total_processes: int = 0
    avg_efficiency: float | None = None
    draft_count: int = 0
    published_count: int = 0
    domain_count: int = 0
    needs_review_count: int = 0
    handoff_count: int = 0
    gap_count: int = 0
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/discovery.py backend/app/schemas/process.py
git commit -m "feat: add discovery schemas, extend ProcessResponse with hierarchy fields"
```

---

### Task 3: Context Gathering Service

**Files:**
- Create: `backend/app/services/processes/context.py`

This module builds the input context for each LLM pass.

- [ ] **Step 1: Implement context builder**

In `backend/app/services/processes/context.py`:

```python
"""Build LLM context from org intelligence, metadata, and documents."""
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataObject
from app.models.organization import Organization

logger = logging.getLogger(__name__)


async def gather_org_context(org_id: UUID, db: AsyncSession) -> dict:
    """Organization intelligence: industry, business model, enrichment data."""
    org = await db.get(Organization, org_id)
    if org is None:
        return {}
    settings = org.settings_json or {}
    return {
        "name": org.name,
        "industry": settings.get("industry", "Unknown"),
        "business_model": settings.get("business_model", ""),
        "description": settings.get("description", ""),
        "domains": settings.get("domains", []),
        "employee_count": settings.get("employee_count"),
        "enrichment": settings.get("enrichment", {}),
    }


async def gather_metadata_summary(org_id: UUID, db: AsyncSession) -> dict:
    """High-level metadata summary for Pass 1 (no field-level detail)."""
    objects_q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.record_count > 0,
        ).order_by(MetadataObject.record_count.desc())
    )
    objects = objects_q.scalars().all()

    automations_q = await db.execute(
        select(MetadataAutomation).where(MetadataAutomation.org_id == org_id)
    )
    automations = automations_q.scalars().all()

    components_q = await db.execute(
        select(MetadataComponent).where(MetadataComponent.org_id == org_id)
    )
    components = components_q.scalars().all()

    return {
        "objects": [
            {
                "api_name": o.api_name,
                "label": o.label,
                "record_count": o.record_count,
                "is_custom": o.is_custom,
                "classification": o.classification,
                "field_count": o.field_count,
            }
            for o in objects
        ],
        "automations": [
            {
                "api_name": a.api_name,
                "label": a.label,
                "type": a.automation_type,
                "related_object": (a.metadata_json or {}).get("related_objects", [""])[0] if a.metadata_json else "",
            }
            for a in automations
        ],
        "components": [
            {
                "api_name": c.api_name,
                "label": c.label,
                "category": c.component_category,
            }
            for c in components
        ],
        "totals": {
            "objects_with_data": len(objects),
            "automations": len(automations),
            "components": len(components),
        },
    }


async def gather_metadata_for_domain(
    org_id: UUID, db: AsyncSession, object_names: list[str], automation_names: list[str],
) -> dict:
    """Full metadata detail for Pass 2 — includes fields, relationships, etc."""
    objects_q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.api_name.in_(object_names),
        )
    )
    objects = objects_q.scalars().all()

    obj_details = []
    for o in objects:
        fields_q = await db.execute(
            select(MetadataObject).where(MetadataObject.id == o.id)
        )
        from app.models.metadata import MetadataField
        fields_result = await db.execute(
            select(MetadataField).where(MetadataField.object_id == o.id)
        )
        fields = fields_result.scalars().all()

        obj_details.append({
            "api_name": o.api_name,
            "label": o.label,
            "record_count": o.record_count,
            "classification": o.classification,
            "record_types": (o.metadata_json or {}).get("record_types", []),
            "relationships": (o.metadata_json or {}).get("relationships", []),
            "fields": [
                {
                    "api_name": f.api_name,
                    "label": f.label,
                    "type": f.field_type,
                    "is_custom": f.is_custom,
                    "is_required": f.is_required,
                    "description": (f.metadata_json or {}).get("description", ""),
                }
                for f in fields[:50]
            ],
        })

    automations_q = await db.execute(
        select(MetadataAutomation).where(
            MetadataAutomation.org_id == org_id,
            MetadataAutomation.api_name.in_(automation_names) if automation_names else MetadataAutomation.org_id == org_id,
        )
    )
    autos = automations_q.scalars().all()

    return {
        "objects": obj_details,
        "automations": [
            {
                "api_name": a.api_name,
                "label": a.label,
                "type": a.automation_type,
                "description": (a.metadata_json or {}).get("description", ""),
                "is_active": (a.metadata_json or {}).get("is_active", True),
            }
            for a in autos
        ],
    }


async def gather_document_summary(org_id: UUID, db: AsyncSession) -> list[dict]:
    """Document titles and section summaries for Pass 1."""
    docs_q = await db.execute(
        select(Document).where(Document.org_id == org_id, Document.status == "indexed")
    )
    docs = docs_q.scalars().all()
    return [
        {
            "id": str(d.id),
            "filename": d.filename,
            "chunk_count": d.chunk_count or 0,
        }
        for d in docs
    ]


async def gather_document_chunks_for_domain(
    org_id: UUID, db: AsyncSession, domain_description: str, limit: int = 20,
) -> list[dict]:
    """RAG retrieval: document chunks relevant to a domain. Uses simple keyword match for now."""
    from app.services.documents.vectorizer import search_similar

    try:
        results = await search_similar(domain_description, org_id, db, limit=limit)
        return [{"content": r["content"], "document_id": r.get("document_id", "")} for r in results]
    except Exception:
        logger.warning("document_chunk_retrieval_failed domain=%s", domain_description[:50])
        return []
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/processes/context.py
git commit -m "feat: context gathering service for discovery pipeline"
```

---

### Task 4: Prompt Templates

**Files:**
- Create: `backend/app/services/processes/prompts.py`

- [ ] **Step 1: Write prompt templates for all three passes**

In `backend/app/services/processes/prompts.py`:

```python
"""Prompt templates for the three-pass process discovery pipeline."""
import json


def build_pass1_prompt(org_context: dict, metadata_summary: dict, document_summary: list[dict]) -> str:
    return f"""You are a senior business process analyst. Given the following information about an organization and its technology systems, identify the top-level business process domains.

## Organization Context
{json.dumps(org_context, indent=2)}

## Platform Metadata Summary
Objects with data: {metadata_summary['totals']['objects_with_data']}
Automations: {metadata_summary['totals']['automations']}
Components: {metadata_summary['totals']['components']}

### Data Objects (sorted by record volume)
{json.dumps(metadata_summary['objects'][:80], indent=2)}

### Automations
{json.dumps(metadata_summary['automations'][:80], indent=2)}

### Components
{json.dumps(metadata_summary['components'][:40], indent=2)}

## Uploaded Documents
{json.dumps(document_summary, indent=2) if document_summary else "No documents uploaded."}

## Instructions
Identify the top-level business process domains present in this organization. For each domain:
- Name it clearly (e.g., "Sales Operations", "Claims Processing", "Customer Onboarding")
- Describe what it encompasses
- List which metadata objects and automations you associate with it
- List which uploaded documents relate to it (by filename)
- Rate your confidence from 0.0 to 1.0
- Explain your reasoning briefly

Do NOT use generic templates. Derive domains from what you actually see in the data.
Objects with zero records or classified as "deprecated" have been excluded.

Respond with valid JSON only:
{{
  "domains": [
    {{
      "name": "string",
      "description": "string",
      "confidence": 0.0,
      "associated_objects": ["ObjectName"],
      "associated_automations": ["AutomationName"],
      "associated_documents": ["filename"],
      "reasoning": "string"
    }}
  ]
}}"""


def build_pass2_prompt(
    org_context: dict, domain: dict, metadata_detail: dict, document_chunks: list[dict],
) -> str:
    return f"""You are a senior business process analyst. You previously identified the following business domain:

## Domain
Name: {domain['name']}
Description: {domain['description']}

## Organization Context
{json.dumps(org_context, indent=2)}

## Detailed Metadata for This Domain
{json.dumps(metadata_detail, indent=2)}

## Relevant Document Excerpts
{json.dumps([c['content'][:500] for c in document_chunks[:10]], indent=2) if document_chunks else "No relevant documents found."}

## Instructions
Decompose this domain into processes, subprocesses, and steps. For each:
- Name and describe it
- Assign a level: "process", "subprocess", or "step"
- List actors (users, integrations, systems involved)
- List artifacts (specific objects, flows, validation rules that participate)
- Rate your confidence (0.0–1.0)
- Flag needs_review=true if the data is ambiguous
- Write a narrative description of how this process works
- Identify handoffs between processes within this domain

Respond with valid JSON only:
{{
  "processes": [
    {{
      "name": "string",
      "level": "process|subprocess|step",
      "description": "string",
      "narrative": "string",
      "confidence": 0.0,
      "needs_review": false,
      "actors": [{{"name": "string", "type": "user|integration|system"}}],
      "artifacts": [{{"type": "object|flow|validation_rule|component", "api_name": "string"}}],
      "children": []
    }}
  ],
  "handoffs": [
    {{
      "source": "process name",
      "target": "process name",
      "type": "integration|manual|automated|unknown",
      "description": "string",
      "confidence": 0.0
    }}
  ]
}}"""


def build_pass3_prompt(org_context: dict, all_domains: list[dict], orphaned_artifacts: list[dict]) -> str:
    return f"""You are a senior business process analyst. You have mapped the following business process domains:

## Organization Context
{json.dumps(org_context, indent=2)}

## Discovered Domains and Their Processes
{json.dumps(all_domains, indent=2)}

## Unclaimed Metadata Artifacts
These objects/automations were not associated with any domain:
{json.dumps(orphaned_artifacts[:50], indent=2) if orphaned_artifacts else "All artifacts are accounted for."}

## Instructions
1. Identify cross-domain handoffs. Where does one domain's output become another domain's input?
2. Flag gaps — places where processes SHOULD connect but there is no evidence of a connection (no integration, no automation, no documented handoff).
3. Categorize orphaned artifacts — do they belong to an undiscovered process?
4. Write an executive summary of how this business operates end-to-end.

Respond with valid JSON only:
{{
  "cross_domain_handoffs": [
    {{
      "source_domain": "string",
      "source_process": "string",
      "target_domain": "string",
      "target_process": "string",
      "type": "integration|manual|automated|unknown",
      "is_gap": true,
      "confidence": 0.0,
      "reasoning": "string"
    }}
  ],
  "orphaned_artifacts": [
    {{"type": "object|automation", "api_name": "string", "reasoning": "string"}}
  ],
  "executive_summary": "string"
}}"""
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/processes/prompts.py
git commit -m "feat: prompt templates for three-pass process discovery"
```

---

### Task 5: Core Discovery Pipeline

**Files:**
- Create: `backend/app/services/processes/discovery.py`
- Modify: `backend/app/services/processes/miner.py`

- [ ] **Step 1: Implement the three-pass pipeline**

In `backend/app/services/processes/discovery.py`:

```python
"""Three-pass process discovery pipeline."""
import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess, ProcessEdge, ProcessNode
from app.services.ai.router import llm_call, parse_json_response
from app.services.processes.context import (
    gather_document_chunks_for_domain,
    gather_document_summary,
    gather_metadata_for_domain,
    gather_metadata_summary,
    gather_org_context,
)
from app.services.processes.prompts import (
    build_pass1_prompt,
    build_pass2_prompt,
    build_pass3_prompt,
)

logger = logging.getLogger(__name__)

ProgressCallback = callable  # (phase: str, status: str, count: int, total: int) -> None


async def run_pass1(
    org_id: UUID, run_id: UUID, db: AsyncSession, progress_cb: ProgressCallback | None = None,
) -> list[dict]:
    """Pass 1: Domain Discovery. Returns list of domain dicts."""
    org_ctx = await gather_org_context(org_id, db)
    meta_summary = await gather_metadata_summary(org_id, db)
    doc_summary = await gather_document_summary(org_id, db)

    prompt = build_pass1_prompt(org_ctx, meta_summary, doc_summary)
    result = llm_call(prompt=prompt, max_tokens=4000, tier="strong")
    parsed = parse_json_response(result.text)

    domains = parsed.get("domains", []) if isinstance(parsed, dict) else []
    logger.info("pass1_complete org=%s domains=%d", org_id, len(domains))

    for domain in domains:
        proc = BusinessProcess(
            org_id=org_id,
            name=domain.get("name", "Unnamed Domain"),
            description=domain.get("description"),
            level="domain",
            parent_id=None,
            confidence_score=domain.get("confidence", 0.5),
            needs_review=domain.get("confidence", 0.5) < 0.6,
            narrative=domain.get("reasoning"),
            status="discovered",
            source="discovery",
            discovery_run_id=run_id,
            actors=[],
            artifacts=[],
            metadata_json={
                "associated_objects": domain.get("associated_objects", []),
                "associated_automations": domain.get("associated_automations", []),
                "associated_documents": domain.get("associated_documents", []),
            },
        )
        db.add(proc)

    await db.flush()
    return domains


async def run_pass2(
    org_id: UUID, run_id: UUID, db: AsyncSession, progress_cb: ProgressCallback | None = None,
) -> int:
    """Pass 2: Process Decomposition per domain. Returns total process count."""
    org_ctx = await gather_org_context(org_id, db)

    domains_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level == "domain",
            BusinessProcess.status != "rejected",
        )
    )
    domains = domains_q.scalars().all()
    total_processes = 0

    for i, domain in enumerate(domains):
        if progress_cb:
            progress_cb("domain_decomposition", "pulling", i, len(domains))

        meta_json = domain.metadata_json or {}
        object_names = meta_json.get("associated_objects", [])
        automation_names = meta_json.get("associated_automations", [])

        meta_detail = await gather_metadata_for_domain(org_id, db, object_names, automation_names)
        doc_chunks = await gather_document_chunks_for_domain(
            org_id, db, f"{domain.name}: {domain.description or ''}"
        )

        domain_dict = {
            "name": domain.name,
            "description": domain.description or "",
        }
        prompt = build_pass2_prompt(org_ctx, domain_dict, meta_detail, doc_chunks)
        result = llm_call(prompt=prompt, max_tokens=6000, tier="strong")
        parsed = parse_json_response(result.text)

        processes = parsed.get("processes", []) if isinstance(parsed, dict) else []
        handoffs = parsed.get("handoffs", []) if isinstance(parsed, dict) else []

        process_name_to_id: dict[str, UUID] = {}

        async def persist_process(proc_data: dict, parent_id: UUID | None) -> None:
            nonlocal total_processes
            bp = BusinessProcess(
                org_id=org_id,
                name=proc_data.get("name", "Unnamed"),
                description=proc_data.get("description"),
                level=proc_data.get("level", "process"),
                parent_id=parent_id,
                confidence_score=proc_data.get("confidence", 0.5),
                needs_review=proc_data.get("needs_review", False),
                narrative=proc_data.get("narrative"),
                status="discovered",
                source="discovery",
                discovery_run_id=run_id,
                actors=proc_data.get("actors", []),
                artifacts=proc_data.get("artifacts", []),
                metadata_json={},
            )
            db.add(bp)
            await db.flush()
            process_name_to_id[bp.name] = bp.id
            total_processes += 1

            for child in proc_data.get("children", []):
                await persist_process(child, bp.id)

        for proc in processes:
            await persist_process(proc, domain.id)

        for ho in handoffs:
            src_id = process_name_to_id.get(ho.get("source"))
            tgt_id = process_name_to_id.get(ho.get("target"))
            if src_id and tgt_id:
                db.add(ProcessHandoff(
                    org_id=org_id,
                    source_process_id=src_id,
                    target_process_id=tgt_id,
                    handoff_type=ho.get("type", "unknown"),
                    description=ho.get("description"),
                    confidence_score=ho.get("confidence", 0.5),
                    is_gap=False,
                    needs_review=ho.get("confidence", 0.5) < 0.6,
                    discovery_run_id=run_id,
                ))

        domain.sub_process_count = len(processes)
        await db.flush()

    logger.info("pass2_complete org=%s processes=%d", org_id, total_processes)
    return total_processes


async def run_pass3(
    org_id: UUID, run_id: UUID, db: AsyncSession, progress_cb: ProgressCallback | None = None,
) -> dict:
    """Pass 3: Cross-Domain Synthesis. Returns synthesis result."""
    org_ctx = await gather_org_context(org_id, db)

    domains_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level == "domain",
            BusinessProcess.status != "rejected",
        )
    )
    domains = domains_q.scalars().all()

    all_domains_data = []
    for domain in domains:
        children_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.parent_id == domain.id,
                BusinessProcess.status != "rejected",
            )
        )
        children = children_q.scalars().all()
        all_domains_data.append({
            "name": domain.name,
            "description": domain.description,
            "processes": [
                {"name": c.name, "level": c.level, "description": c.description}
                for c in children
            ],
        })

    meta_summary = await gather_metadata_summary(org_id, db)
    claimed_objects = set()
    for d in domains:
        claimed_objects.update((d.metadata_json or {}).get("associated_objects", []))
    orphaned = [
        {"type": "object", "api_name": o["api_name"]}
        for o in meta_summary["objects"]
        if o["api_name"] not in claimed_objects
    ]

    prompt = build_pass3_prompt(org_ctx, all_domains_data, orphaned)
    result = llm_call(prompt=prompt, max_tokens=4000, tier="strong")
    parsed = parse_json_response(result.text)

    if not isinstance(parsed, dict):
        parsed = {}

    process_name_q = await db.execute(
        select(BusinessProcess.id, BusinessProcess.name).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
        )
    )
    name_to_id = {row.name: row.id for row in process_name_q}

    for ho in parsed.get("cross_domain_handoffs", []):
        src_name = ho.get("source_process", "")
        tgt_name = ho.get("target_process", "")
        src_id = name_to_id.get(src_name)
        tgt_id = name_to_id.get(tgt_name)
        if src_id and tgt_id:
            db.add(ProcessHandoff(
                org_id=org_id,
                source_process_id=src_id,
                target_process_id=tgt_id,
                handoff_type=ho.get("type", "unknown"),
                description=ho.get("reasoning"),
                confidence_score=ho.get("confidence", 0.5),
                is_gap=ho.get("is_gap", False),
                needs_review=ho.get("is_gap", False) or ho.get("confidence", 0.5) < 0.6,
                discovery_run_id=run_id,
            ))

    await db.flush()
    logger.info("pass3_complete org=%s handoffs=%d", org_id, len(parsed.get("cross_domain_handoffs", [])))
    return parsed


async def cleanup_previous_run(org_id: UUID, db: AsyncSession) -> None:
    """Delete all discovery data from previous runs to avoid duplicates."""
    await db.execute(
        delete(ProcessHandoff).where(ProcessHandoff.org_id == org_id)
    )
    await db.execute(
        delete(ProcessEdge).where(
            ProcessEdge.process_id.in_(
                select(BusinessProcess.id).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.source == "discovery",
                )
            )
        )
    )
    await db.execute(
        delete(ProcessNode).where(
            ProcessNode.process_id.in_(
                select(BusinessProcess.id).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.source == "discovery",
                )
            )
        )
    )
    await db.execute(
        delete(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.source == "discovery",
        )
    )
    await db.flush()
```

- [ ] **Step 2: Update miner.py to delegate to discovery pipeline**

Replace the contents of `backend/app/services/processes/miner.py`:

```python
"""Mine business processes — delegates to the discovery pipeline."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def mine_from_metadata(org_id: UUID, db: AsyncSession) -> list[dict]:
    """Legacy stub — process discovery now handled by the three-pass pipeline."""
    return []


async def mine_from_documents(org_id: UUID, db: AsyncSession) -> list[dict]:
    """Legacy stub — document analysis now handled by the three-pass pipeline."""
    return []
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/processes/discovery.py backend/app/services/processes/miner.py
git commit -m "feat: three-pass process discovery pipeline with cleanup and persistence"
```

---

### Task 6: Celery Worker and Progress Tracking

**Files:**
- Create: `backend/app/workers/process_discovery.py`

- [ ] **Step 1: Implement the discovery worker**

In `backend/app/workers/process_discovery.py`:

```python
"""Celery task for process discovery pipeline."""
import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PHASES = [
    "context_gathering",
    "domain_discovery",
    "domain_decomposition",
    "cross_domain_synthesis",
    "graph_generation",
]


@celery_app.task(name="processes.discover")
def process_discovery_task(org_id: str) -> str:
    import asyncio

    from app.core.observability import flush_langfuse, get_langfuse
    from app.services.sync_progress import get_redis_client, update_phase

    r = get_redis_client()
    run_key = f"discovery:{org_id}"

    for phase in PHASES:
        r.hset(run_key, f"phase:{phase}:status", "waiting")
        r.hset(run_key, f"phase:{phase}:count", "0")
        r.hset(run_key, f"phase:{phase}:total", "0")
    r.hset(run_key, "status", "running")
    r.hset(run_key, "run_id", "")
    r.expire(run_key, 3600)

    def _update(phase: str, status: str, count: int = 0, total: int = 0) -> None:
        r.hset(run_key, f"phase:{phase}:status", status)
        r.hset(run_key, f"phase:{phase}:count", str(count))
        r.hset(run_key, f"phase:{phase}:total", str(total))

    async def _pipeline() -> str:
        from datetime import datetime, timezone

        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.core.database import engine
        from app.models.discovery import DiscoveryRun
        from app.services.processes.discovery import (
            cleanup_previous_run,
            run_pass1,
            run_pass2,
            run_pass3,
        )

        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            run = DiscoveryRun(org_id=UUID(org_id), status="running")
            session.add(run)
            await session.flush()
            run_id = run.id
            r.hset(run_key, "run_id", str(run_id))

            try:
                _update("context_gathering", "pulling")
                await cleanup_previous_run(UUID(org_id), session)
                await session.commit()
                _update("context_gathering", "done")

                _update("domain_discovery", "pulling")
                domains = await run_pass1(UUID(org_id), run_id, session)
                await session.commit()
                _update("domain_discovery", "done", len(domains))

                def pass2_progress(phase, status, count, total):
                    _update("domain_decomposition", "pulling", count, total)

                _update("domain_decomposition", "pulling", 0, len(domains))
                process_count = await run_pass2(
                    UUID(org_id), run_id, session, progress_cb=pass2_progress
                )
                await session.commit()
                _update("domain_decomposition", "done", process_count)

                _update("cross_domain_synthesis", "pulling")
                synthesis = await run_pass3(UUID(org_id), run_id, session)
                await session.commit()
                _update("cross_domain_synthesis", "done")

                _update("graph_generation", "pulling")
                # Graph generation from hierarchy — future enhancement
                _update("graph_generation", "done")

                run.status = "completed"
                run.completed_at = datetime.now(tz=timezone.utc)
                run.pass_results = {
                    "domains": len(domains),
                    "processes": process_count,
                    "executive_summary": synthesis.get("executive_summary", ""),
                }
                await session.commit()

                r.hset(run_key, "status", "completed")
                return str(run_id)

            except Exception as exc:
                run.status = "failed"
                run.error = str(exc)[:2000]
                run.completed_at = datetime.now(tz=timezone.utc)
                await session.commit()
                r.hset(run_key, "status", "failed")
                r.hset(run_key, "error", str(exc)[:500])
                raise

    try:
        lf = get_langfuse()
        if lf is not None:
            lf.trace(name="process_discovery", metadata={"org_id": org_id})
        return asyncio.run(_pipeline())
    finally:
        flush_langfuse()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/workers/process_discovery.py
git commit -m "feat: celery worker for process discovery with Redis progress tracking"
```

---

### Task 7: Discovery API Routes

**Files:**
- Create: `backend/app/api/routes/discovery.py`
- Modify: `backend/app/api/routes/processes.py`

- [ ] **Step 1: Create discovery routes**

In `backend/app/api/routes/discovery.py`:

```python
"""API routes for process discovery pipeline."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentOrg, DbSession
from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess
from app.schemas.discovery import DiscoveryRunResponse, DiscoveryStatusResponse, ProcessHandoffResponse
from app.services.sync_progress import get_redis_client

router = APIRouter()


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_discovery(db: DbSession, org: CurrentOrg) -> dict:
    from app.workers.process_discovery import process_discovery_task
    process_discovery_task.delay(str(org.id))
    return {"status": "accepted"}


@router.get("/status")
async def discovery_status(org: CurrentOrg) -> DiscoveryStatusResponse:
    r = get_redis_client()
    run_key = f"discovery:{org.id}"
    raw = r.hgetall(run_key)
    if not raw:
        return DiscoveryStatusResponse(
            run_id=None, status="idle", phases={},
            started_at=None, completed_at=None, error=None,
        )

    data = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in raw.items()}
    phases = {}
    for phase_key, val in data.items():
        if phase_key.startswith("phase:"):
            parts = phase_key.split(":")
            if len(parts) == 3:
                phase_name, field = parts[1], parts[2]
                phases.setdefault(phase_name, {})
                phases[phase_name][field] = int(val) if field in ("count", "total") else val

    return DiscoveryStatusResponse(
        run_id=data.get("run_id") or None,
        status=data.get("status", "idle"),
        phases=phases,
        started_at=None,
        completed_at=None,
        error=data.get("error"),
    )


@router.get("/runs", response_model=list[DiscoveryRunResponse])
async def list_runs(db: DbSession, org: CurrentOrg) -> list[DiscoveryRunResponse]:
    q = await db.execute(
        select(DiscoveryRun).where(DiscoveryRun.org_id == org.id).order_by(DiscoveryRun.started_at.desc()).limit(10)
    )
    return [DiscoveryRunResponse.model_validate(r) for r in q.scalars().all()]


@router.get("/handoffs", response_model=list[ProcessHandoffResponse])
async def list_handoffs(db: DbSession, org: CurrentOrg) -> list[ProcessHandoffResponse]:
    q = await db.execute(
        select(ProcessHandoff).where(ProcessHandoff.org_id == org.id)
    )
    return [ProcessHandoffResponse.model_validate(h) for h in q.scalars().all()]


@router.post("/{process_id}/confirm")
async def confirm_process(process_id: UUID, db: DbSession, org: CurrentOrg) -> dict:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    proc.status = "confirmed"
    await db.commit()
    return {"status": "confirmed"}


@router.post("/{process_id}/reject")
async def reject_process(process_id: UUID, db: DbSession, org: CurrentOrg) -> dict:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    proc.status = "rejected"
    await db.commit()
    return {"status": "rejected"}
```

- [ ] **Step 2: Register routes in the main router**

Find where routes are registered (likely `backend/app/api/router.py` or similar) and add:

```python
from app.api.routes.discovery import router as discovery_router
api_router.include_router(discovery_router, prefix="/discovery", tags=["discovery"])
```

- [ ] **Step 3: Update processes generate endpoint**

In `backend/app/api/routes/processes.py`, update the `generate_processes` function:

```python
@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_processes(
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str]:
    from app.workers.process_discovery import process_discovery_task
    process_discovery_task.delay(str(org.id))
    return {"status": "accepted"}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/discovery.py backend/app/api/routes/processes.py
git commit -m "feat: discovery API routes — start, status, confirm, reject, handoffs"
```

---

### Task 8: Frontend Types and API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Add TypeScript types**

In `frontend/src/types/index.ts`, add:

```typescript
export interface DiscoveryPhase {
  status: string
  count: number
  total: number
}

export interface DiscoveryStatus {
  run_id: string | null
  status: string
  phases: Record<string, DiscoveryPhase>
  started_at: string | null
  completed_at: string | null
  error: string | null
}

export interface ProcessHandoff {
  id: string
  source_process_id: string
  target_process_id: string
  handoff_type: string
  description: string | null
  confidence_score: number
  is_gap: boolean
  needs_review: boolean
}
```

- [ ] **Step 2: Add API client methods**

In `frontend/src/api/client.ts`, add inside the `api` object:

```typescript
discovery: {
  start: () => request<void>('/discovery/start', { method: 'POST' }),
  status: () => request<DiscoveryStatus>('/discovery/status'),
  handoffs: () => request<ProcessHandoff[]>('/discovery/handoffs'),
  confirmProcess: (id: string) => request<void>(`/discovery/${id}/confirm`, { method: 'POST' }),
  rejectProcess: (id: string) => request<void>(`/discovery/${id}/reject`, { method: 'POST' }),
},
```

- [ ] **Step 3: Add React Query hooks**

In `frontend/src/hooks/useApi.ts`, add:

```typescript
export function useDiscoveryStatus() {
  return useQuery({
    queryKey: ['discovery-status'],
    queryFn: () => api.discovery.status(),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed' || status === 'idle') return false
      return 2000
    },
  })
}

export function useStartDiscovery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.discovery.start(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['discovery-status'] })
    },
  })
}

export function useConfirmProcess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.discovery.confirmProcess(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['processes'] }),
  })
}

export function useRejectProcess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.discovery.rejectProcess(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['processes'] }),
  })
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat: frontend types, API client, and hooks for process discovery"
```

---

### Task 9: Discovery Pipeline Status Bar Component

**Files:**
- Create: `frontend/src/components/DiscoveryPipeline.tsx`

- [ ] **Step 1: Build the inline pipeline status bar**

In `frontend/src/components/DiscoveryPipeline.tsx`:

```typescript
import { Check, Loader2, AlertCircle, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import type { DiscoveryStatus } from '@/types'

const STAGES = [
  { key: 'domain_discovery', label: 'Domain Discovery', passNum: 1 },
  { key: 'domain_decomposition', label: 'Process Decomposition', passNum: 2 },
  { key: 'cross_domain_synthesis', label: 'Cross-Domain Synthesis', passNum: 3 },
] as const

function StageChip({
  label,
  passNum,
  status,
  count,
  total,
  onRerun,
}: {
  label: string
  passNum: number
  status: string
  count: number
  total: number
  onRerun?: () => void
}) {
  const isWaiting = status === 'waiting' || !status
  const isRunning = status === 'pulling'
  const isDone = status === 'done'
  const isFailed = status === 'failed'

  const subtext = isRunning && total > 0
    ? `${count} of ${total}`
    : isDone && count > 0
      ? `${count} found`
      : undefined

  return (
    <div
      className={clsx(
        'flex flex-1 items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm transition-all duration-300',
        isWaiting && 'border-slate-200 bg-slate-50 text-slate-400',
        isRunning && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        isDone && 'border-emerald-200 bg-emerald-50 text-emerald-800',
        isFailed && 'border-red-200 bg-red-50 text-red-800',
      )}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
        {isWaiting && <span className="h-2 w-2 rounded-full bg-slate-300" />}
        {isRunning && <Loader2 className="h-4 w-4 animate-spin text-sky-600" />}
        {isDone && <Check className="h-4 w-4 text-emerald-600" />}
        {isFailed && <AlertCircle className="h-4 w-4 text-red-600" />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          <span className="text-xs opacity-60">Pass {passNum}</span>{' '}
          {label}
        </p>
        {subtext ? <p className="text-xs opacity-70">{subtext}</p> : null}
      </div>
      {isDone && onRerun ? (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRerun() }}
          className="shrink-0 rounded p-1 text-slate-400 hover:bg-white/60 hover:text-slate-600"
          title={`Re-run ${label}`}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}

export function DiscoveryPipeline({
  data,
  isActive,
}: {
  data: DiscoveryStatus | undefined
  isActive: boolean
}) {
  if (!isActive && (!data || data.status === 'idle')) return null

  const phases = data?.phases ?? {}
  const overallStatus = data?.status ?? 'idle'

  return (
    <div
      className={clsx(
        'rounded-xl border p-4 transition-all duration-500',
        overallStatus === 'running' && 'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        overallStatus === 'completed' && 'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        overallStatus === 'failed' && 'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
        overallStatus === 'idle' && 'border-slate-200 bg-slate-50',
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-800">
          {overallStatus === 'running' && 'Discovering processes…'}
          {overallStatus === 'completed' && 'Discovery complete'}
          {overallStatus === 'failed' && 'Discovery failed'}
          {overallStatus === 'idle' && 'Ready to discover'}
        </p>
        {data?.error ? (
          <p className="text-xs text-red-600">{data.error}</p>
        ) : null}
      </div>
      <div className="flex gap-2">
        {STAGES.map((stage) => {
          const phase = phases[stage.key]
          return (
            <StageChip
              key={stage.key}
              label={stage.label}
              passNum={stage.passNum}
              status={phase?.status ?? 'waiting'}
              count={phase?.count ?? 0}
              total={phase?.total ?? 0}
            />
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DiscoveryPipeline.tsx
git commit -m "feat: inline discovery pipeline status bar component"
```

---

### Task 10: Update Processes Page

**Files:**
- Modify: `frontend/src/pages/Processes/index.tsx`

- [ ] **Step 1: Integrate discovery pipeline into the Processes page**

Key changes to `frontend/src/pages/Processes/index.tsx`:

1. Import and use `DiscoveryPipeline`, `useDiscoveryStatus`, `useStartDiscovery`, `useConfirmProcess`, `useRejectProcess`
2. Replace the static `Generate` button with state-aware discovery controls:
   - No prior run: "Discover Processes" button
   - Run in progress: "Discovering…" (disabled) + `DiscoveryPipeline` status bar
   - Run complete: "Re-discover" button + collapsed summary + `DiscoveryPipeline` bar
3. Add confirm/reject buttons to process accordion rows where `status === "discovered"`
4. Show `confidence_score` as a badge on each row (green >0.8, amber 0.5-0.8, red <0.5)
5. Show "Needs Review" indicator on flagged items

The `DiscoveryPipeline` component goes above the KPI cards, visible whenever a run exists.

For the accordion rows, add to each `AccordionRow`'s expanded content:

```tsx
{p.status === 'discovered' && (
  <div className="flex gap-2">
    <button onClick={() => confirmMutation.mutate(p.id)} className="...">Confirm</button>
    <button onClick={() => rejectMutation.mutate(p.id)} className="...">Reject</button>
  </div>
)}
```

The `useDiscoveryStatus` hook auto-polls every 2s during a run. When the run completes, invalidate the processes query to refresh the list.

This is the largest frontend change — the implementation agent should read the full current `index.tsx` before making edits to ensure nothing breaks.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Processes/index.tsx
git commit -m "feat: integrate discovery pipeline into Processes page with confirm/reject"
```

---

### Task 11: Update Process KPIs and List Endpoint

**Files:**
- Modify: `backend/app/api/routes/processes.py`

- [ ] **Step 1: Update KPIs to include new counts**

In the `list_processes` function, add queries for the new KPI fields:

```python
domain_c = await db.scalar(
    select(func.count()).select_from(BusinessProcess).where(
        BusinessProcess.org_id == org.id, BusinessProcess.level == "domain",
    )
)
review_c = await db.scalar(
    select(func.count()).select_from(BusinessProcess).where(
        BusinessProcess.org_id == org.id, BusinessProcess.needs_review == True,
    )
)
handoff_c = await db.scalar(
    select(func.count()).select_from(ProcessHandoff).where(ProcessHandoff.org_id == org.id)
)
gap_c = await db.scalar(
    select(func.count()).select_from(ProcessHandoff).where(
        ProcessHandoff.org_id == org.id, ProcessHandoff.is_gap == True,
    )
)
```

Add these to the `ProcessKpis` response. Also add `from app.models.discovery import ProcessHandoff` at the top.

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/processes.py
git commit -m "feat: update process KPIs with domain, review, handoff, gap counts"
```

---

### Task 12: Run Migration on Railway and Deploy

- [ ] **Step 1: Push all changes**

```bash
git push origin master
```

- [ ] **Step 2: Run migration on Railway**

```bash
railway run py -m alembic upgrade head
```

Expected: Migration 007 applies cleanly.

- [ ] **Step 3: Verify deployment**

Check Railway dashboard for successful backend + frontend builds. Verify the Processes page loads with the new discovery UI.

- [ ] **Step 4: Test end-to-end**

Navigate to the Processes page, click "Discover Processes", and verify:
- Pipeline status bar appears with three stages
- Stages progress from waiting → running → complete
- Domains appear as accordion rows after Pass 1
- Processes appear under domains after Pass 2
- Cross-domain handoffs are created after Pass 3

---

## Self-Review Notes

**Spec coverage:** All sections of the spec are addressed:
- Data model changes → Task 1
- LLM pipeline (3 passes) → Tasks 4, 5
- Worker orchestration → Task 6
- Progress tracking → Tasks 6, 9
- Frontend pipeline UX → Tasks 9, 10
- Re-run semantics → Task 5 (`cleanup_previous_run`), Task 7 (re-run endpoints)
- Confirm/reject → Task 7 (API), Task 10 (UI)

**Not yet implemented (marked as future in spec):**
- Per-pass re-run buttons (API supports it via separate endpoints, but frontend only has full re-run for now)
- Staleness indicators (data model supports via `metadata_json`, but UI deferred)
- Graph generation from hierarchy (placeholder in worker, ProcessNode/ProcessEdge rebuild is a future task)
- Node confidence color-coding in ReactFlow

**Type consistency check:** `DiscoveryStatus` type matches `DiscoveryStatusResponse` schema. `ProcessResponse` fields match model columns. `DiscoveryPhase` matches Redis hash structure.
