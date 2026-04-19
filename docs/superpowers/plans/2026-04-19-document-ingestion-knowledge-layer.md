# Document Ingestion & Knowledge Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add content hashing, NLP concept extraction, community detection, community-aware retrieval, provenance tracking, amendment notifications, enhanced delete, and a Smart Document Library UI to the Arcflare platform.

**Architecture:** Extends the existing Celery-based document vectorization pipeline with three new post-embedding steps (concept extraction via spaCy, co-occurrence graph construction with PMI weighting, Leiden community detection). New Postgres tables store concepts, co-occurrences, communities, and provenance links. Frontend gets a new `/documents` page with upload, list, detail, search, and delete. Community-aware retrieval replaces flat vector search in process discovery and chat.

**Tech Stack:** Python (spaCy, leidenalg, igraph), PostgreSQL + pgvector, Celery, React + TanStack Query + Tailwind CSS

**Spec:** [`docs/superpowers/specs/2026-04-19-document-ingestion-knowledge-layer-design.md`](docs/superpowers/specs/2026-04-19-document-ingestion-knowledge-layer-design.md)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/alembic/versions/016_knowledge_layer.py` | Migration: new tables (concepts, concept_cooccurrences, communities, chunk_communities, process_document_sources) + new columns on documents and document_chunks |
| `backend/app/models/knowledge.py` | SQLAlchemy models: Concept, ConceptCooccurrence, Community, ChunkCommunity, ProcessDocumentSource |
| `backend/app/services/documents/concepts.py` | NLP concept extraction: spaCy noun phrase extraction, normalization, co-occurrence graph construction, PMI computation |
| `backend/app/services/documents/communities.py` | Leiden community detection: graph loading, Leiden execution, community CRUD, chunk-community linking |
| `backend/app/services/documents/notifications.py` | Amendment notifications: identify affected processes when new doc is indexed |
| `backend/app/schemas/knowledge.py` | Pydantic schemas for concepts, communities, provenance |
| `frontend/src/pages/Documents/index.tsx` | Smart Document Library page: upload zone, document list, filters |
| `frontend/src/pages/Documents/DocumentDetail.tsx` | Document detail slide-over: metadata, communities, provenance, tags |
| `frontend/src/pages/Documents/UploadZone.tsx` | Drag-and-drop upload component with progress |

### Modified Files

| File | Changes |
|------|---------|
| `backend/requirements.txt` | Add spacy, leidenalg, igraph |
| `backend/app/models/__init__.py` | Import new knowledge models |
| `backend/app/models/document.py` | Add content_hash, concept_count, community_ids, embedding_model columns to Document; add concept_ids, content_hash to DocumentChunk |
| `backend/app/services/documents/upload.py` | Add SHA-256 streaming hash + dedup check |
| `backend/app/workers/vectorization.py` | Add concept extraction, community detection, notification steps after embedding |
| `backend/app/api/routes/documents.py` | Fix upload path, add disk cleanup on delete, add community/provenance endpoints |
| `backend/app/services/processes/context.py` | Replace flat vector search with community-aware retrieval |
| `backend/app/services/chat/context.py` | Add community context to RAG results |
| `frontend/src/App.tsx` | Add `/documents` route |
| `frontend/src/api/client.ts` | Fix upload path (`/documents` → `/documents/upload`), add community/provenance API methods |
| `frontend/src/types/index.ts` | Add Document, Community, Provenance types |
| `frontend/src/components/AppLayout.tsx` | Add Documents nav link |

---

## Task 1: Database Migration + Models

**Files:**
- Create: `backend/alembic/versions/016_knowledge_layer.py`
- Create: `backend/app/models/knowledge.py`
- Modify: `backend/app/models/document.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the knowledge models file**

Create `backend/app/models/knowledge.py`:

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    concept_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="noun_phrase"
    )
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        {"comment": "Extracted noun phrases / concepts from document chunks"},
    )


class ConceptCooccurrence(Base):
    __tablename__ = "concept_cooccurrences"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_a_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept_b_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    pmi_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class Community(Base):
    __tablename__ = "communities"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("communities.id", ondelete="SET NULL"),
        nullable=True,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    member_concept_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChunkCommunity(Base):
    __tablename__ = "chunk_communities"

    chunk_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    community_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("communities.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ProcessDocumentSource(Base):
    __tablename__ = "process_document_sources"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    chunk_content_hashes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Add new columns to Document and DocumentChunk models**

Modify `backend/app/models/document.py` — add these columns to the `Document` class after the existing `chunk_count` column:

```python
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    concept_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    community_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
```

Add these columns to the `DocumentChunk` class after `metadata_json`:

```python
    concept_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 3: Register models in `__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.knowledge import (
    ChunkCommunity,
    Community,
    Concept,
    ConceptCooccurrence,
    ProcessDocumentSource,
)
```

- [ ] **Step 4: Create Alembic migration**

Create `backend/alembic/versions/016_knowledge_layer.py`:

```python
"""knowledge layer: concepts, communities, provenance

Revision ID: 016
Revises: 015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- New tables ---
    op.create_table(
        "concepts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=True),
        sa.Column("concept_type", sa.String(50), nullable=False, server_default="noun_phrase"),
        sa.Column("frequency", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_concepts_org_name", "concepts", ["org_id", "name"])

    op.create_table(
        "concept_cooccurrences",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("concept_a_id", UUID(as_uuid=True), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept_b_id", UUID(as_uuid=True), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pmi_weight", sa.Float, nullable=True),
        sa.Column("document_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_unique_constraint(
        "uq_cooccurrence_org_pair",
        "concept_cooccurrences",
        ["org_id", "concept_a_id", "concept_b_id"],
    )

    op.create_table(
        "communities",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("communities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("label", sa.String(512), nullable=True),
        sa.Column("member_concept_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chunk_communities",
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("community_id", UUID(as_uuid=True), sa.ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "process_document_sources",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("chunk_content_hashes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Alter existing tables ---
    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True, index=True))
    op.add_column("documents", sa.Column("concept_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("community_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("documents", sa.Column("embedding_model", sa.String(128), nullable=True))

    op.add_column("document_chunks", sa.Column("concept_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("document_chunks", sa.Column("content_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "content_hash")
    op.drop_column("document_chunks", "concept_ids")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "community_ids")
    op.drop_column("documents", "concept_count")
    op.drop_column("documents", "content_hash")
    op.drop_table("process_document_sources")
    op.drop_table("chunk_communities")
    op.drop_table("communities")
    op.drop_table("concept_cooccurrences")
    op.drop_table("concepts")
```

- [ ] **Step 5: Run the migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration 016 applies successfully, all new tables created, all existing table alterations applied.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/016_knowledge_layer.py backend/app/models/knowledge.py backend/app/models/document.py backend/app/models/__init__.py
git commit -m "feat: add knowledge layer DB models and migration (concepts, communities, provenance)"
```

---

## Task 2: Dependencies + spaCy Model

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add Python dependencies**

Add to `backend/requirements.txt`:

```
spacy>=3.7.0
leidenalg>=0.10.0
python-igraph>=0.11.0
```

- [ ] **Step 2: Install and download spaCy model**

Run: `cd backend && pip install -r requirements.txt && python -m spacy download en_core_web_sm`
Expected: All packages install. spaCy model downloads (~12MB).

- [ ] **Step 3: Verify spaCy works**

Run: `cd backend && python -c "import spacy; nlp = spacy.load('en_core_web_sm'); doc = nlp('The Sales Manager reviews discount requests in Salesforce CPQ.'); print([chunk.text for chunk in doc.noun_chunks])"`
Expected: Output includes noun phrases like `['The Sales Manager', 'discount requests', 'Salesforce CPQ']`

- [ ] **Step 4: Verify Leiden works**

Run: `cd backend && python -c "import igraph; import leidenalg; g = igraph.Graph.Famous('Petersen'); part = leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition, resolution_parameter=1.0); print(f'Communities: {len(part)}, Quality: {part.quality():.4f}')"`
Expected: Output shows communities found on the Petersen graph.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add spacy, leidenalg, igraph dependencies for knowledge layer"
```

---

## Task 3: Content Hashing & Dedup + Schema Updates

**Files:**
- Modify: `backend/app/services/documents/upload.py`
- Modify: `backend/app/api/routes/documents.py`
- Modify: `backend/app/schemas/document.py`

- [ ] **Step 1: Add streaming SHA-256 to upload handler**

Replace the contents of `backend/app/services/documents/upload.py` with:

```python
"""Handle multipart uploads with content hashing and dedup."""

import hashlib
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def handle_upload(
    file: UploadFile,
    org_id: UUID,
    user_id: UUID | None,
    db: AsyncSession,
    upload_root: str = "uploads",
) -> tuple[Document, bool]:
    """Stream upload to disk, compute hash, dedup, create Document record.

    Returns (document, is_new). If is_new is False, the returned document
    is an existing duplicate and no file was written.
    """
    safe_name = Path(file.filename or "unnamed").name
    doc_id = uuid.uuid4()
    dest_dir = Path(upload_root) / str(org_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{doc_id}_{safe_name}"

    sha256 = hashlib.sha256()
    size = 0
    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            sha256.update(chunk)
            out.write(chunk)

    content_hash = sha256.hexdigest()

    existing = await db.scalar(
        select(Document).where(
            Document.org_id == org_id,
            Document.content_hash == content_hash,
            Document.status == "indexed",
        )
    )
    if existing:
        dest_path.unlink(missing_ok=True)
        return existing, False

    from app.core.config import get_settings
    settings = get_settings()

    doc = Document(
        id=doc_id,
        org_id=org_id,
        filename=safe_name,
        mime_type=file.content_type,
        file_size_bytes=size,
        storage_path=str(dest_path.resolve()),
        status="uploaded",
        uploaded_by=user_id,
        tags=[],
        chunk_count=0,
        content_hash=content_hash,
        embedding_model=settings.EMBEDDING_MODEL,
    )
    db.add(doc)
    await db.flush()
    return doc, True
```

- [ ] **Step 2: Update document schemas to include new fields**

In `backend/app/schemas/document.py`, add the new columns to both response schemas:

Add to `DocumentUploadResponse` after `chunk_count`:

```python
    content_hash: str | None = None
    concept_count: int = 0
    community_ids: list = Field(default_factory=list)
    embedding_model: str | None = None
```

Add the same fields to `DocumentResponse` after `chunk_count`:

```python
    content_hash: str | None = None
    concept_count: int = 0
    community_ids: list = Field(default_factory=list)
    embedding_model: str | None = None
```

- [ ] **Step 3: Update the upload route to handle dedup response**

In `backend/app/api/routes/documents.py`, the current upload handler (lines 28-41) calls `handle_upload` and gets back a single `Document`. The new version returns `(Document, bool)`. Update lines 38-41:

Replace:
```python
    doc = await handle_upload(file, org.id, user_id, db)
    await db.commit()
    vectorize_document_task.delay(str(doc.id))
    return DocumentUploadResponse.model_validate(doc)
```

With:
```python
    doc, is_new = await handle_upload(file, org.id, user_id, db)
    await db.commit()
    if is_new:
        vectorize_document_task.delay(str(doc.id))
    return DocumentUploadResponse.model_validate(doc)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/documents/upload.py backend/app/api/routes/documents.py backend/app/schemas/document.py
git commit -m "feat: add SHA-256 content hashing and dedup to document upload"
```

---

## Task 4: Enhanced Delete with Disk Cleanup + Concept Teardown

**Files:**
- Modify: `backend/app/api/routes/documents.py`

- [ ] **Step 1: Enhance the delete route**

Replace the existing `delete_document` function in `backend/app/api/routes/documents.py`:

```python
@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> None:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.storage_path:
        from pathlib import Path
        path = Path(doc.storage_path)
        path.unlink(missing_ok=True)

    await db.delete(doc)
    await db.commit()
```

Note: The cascade deletes handle chunks → chunk_communities. Concept frequency decrements and co-occurrence cleanup will be handled by a post-delete Celery task added in Task 6.

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/documents.py
git commit -m "fix: delete document file from disk on document deletion"
```

---

## Task 5: NLP Concept Extraction Service

**Files:**
- Create: `backend/app/services/documents/concepts.py`

- [ ] **Step 1: Create the concept extraction module**

Create `backend/app/services/documents/concepts.py`:

```python
"""NLP concept extraction following GraphRAG's SyntacticNounPhraseExtractor pattern."""

import hashlib
import logging
import math
from itertools import combinations
from uuid import UUID

import spacy
from spacy.util import filter_spans
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.knowledge import Concept, ConceptCooccurrence

logger = logging.getLogger(__name__)

_nlp = None

STOPWORD_CONCEPTS = frozenset({
    "thing", "things", "way", "ways", "time", "times", "example",
    "part", "parts", "number", "lot", "kind", "type", "case",
    "point", "fact", "result", "end", "use",
})
MIN_CONCEPT_LEN = 2
MAX_CONCEPT_LEN = 100
MIN_COOCCURRENCE_FOR_PMI = 2


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", exclude=["lemmatizer"])
    return _nlp


def extract_noun_phrases(text_content: str) -> list[tuple[str, str]]:
    """Extract noun phrases from text. Returns list of (canonical_name, display_name)."""
    nlp = _get_nlp()
    doc = nlp(text_content[:100_000])

    ent_spans = list(doc.ents)
    chunk_spans = list(doc.noun_chunks)
    merged = filter_spans(ent_spans + chunk_spans)

    results: list[tuple[str, str]] = []
    for span in merged:
        display = span.text.strip()
        if len(display) < MIN_CONCEPT_LEN or len(display) > MAX_CONCEPT_LEN:
            continue
        if not any(t.pos_ in ("NOUN", "PROPN") for t in span):
            continue
        canonical = display.upper()
        if canonical.lower() in STOPWORD_CONCEPTS:
            continue
        results.append((canonical, display))

    return results


async def extract_and_store_concepts(
    chunks: list[dict],
    document_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> int:
    """Extract concepts from chunks, build co-occurrence graph.

    Each chunk dict must have 'content' (str) and 'chunk_db_id' (UUID).
    Returns total concept count for the document.
    """
    all_chunk_concepts: list[list[tuple[str, str]]] = []
    doc_concept_set: set[str] = set()

    for chunk in chunks:
        content = chunk.get("content") or ""
        if not content.strip():
            all_chunk_concepts.append([])
            continue
        phrases = extract_noun_phrases(content)
        all_chunk_concepts.append(phrases)
        for canonical, _ in phrases:
            doc_concept_set.add(canonical)

    if not doc_concept_set:
        return 0

    concept_id_map: dict[str, UUID] = {}
    for canonical, display in {c: d for concepts in all_chunk_concepts for c, d in concepts}.items():
        stmt = pg_insert(Concept.__table__).values(
            org_id=org_id,
            name=canonical,
            display_name=display,
            concept_type="noun_phrase",
            frequency=1,
        ).on_conflict_do_update(
            constraint="uq_concepts_org_name",
            set_={"frequency": Concept.__table__.c.frequency + 1},
        ).returning(Concept.__table__.c.id)
        result = await db.execute(stmt)
        concept_id_map[canonical] = result.scalar_one()

    for i, chunk in enumerate(chunks):
        chunk_phrases = all_chunk_concepts[i]
        if not chunk_phrases:
            continue
        chunk_concept_ids = [str(concept_id_map[c]) for c, _ in chunk_phrases]

        chunk_db_id = chunk["chunk_db_id"]
        await db.execute(
            text("UPDATE document_chunks SET concept_ids = :ids, content_hash = :hash WHERE id = :cid"),
            {
                "ids": chunk_concept_ids,
                "hash": hashlib.sha256((chunk.get("content") or "").encode()).hexdigest(),
                "cid": str(chunk_db_id),
            },
        )

        canonical_names = list({c for c, _ in chunk_phrases})
        for a, b in combinations(sorted(canonical_names), 2):
            a_id, b_id = concept_id_map[a], concept_id_map[b]
            if a_id > b_id:
                a_id, b_id = b_id, a_id
            stmt = pg_insert(ConceptCooccurrence.__table__).values(
                org_id=org_id,
                concept_a_id=a_id,
                concept_b_id=b_id,
                raw_weight=1,
                document_ids=[str(document_id)],
            ).on_conflict_do_update(
                constraint="uq_cooccurrence_org_pair",
                set_={
                    "raw_weight": ConceptCooccurrence.__table__.c.raw_weight + 1,
                    "document_ids": text(
                        "concept_cooccurrences.document_ids || :new_doc_id::jsonb"
                    ),
                },
            )
            await db.execute(stmt, {"new_doc_id": f'["{document_id}"]'})

    await db.flush()
    return len(doc_concept_set)


async def compute_pmi_weights(org_id: UUID, db: AsyncSession) -> None:
    """Recompute PMI weights for all co-occurrence edges in an org."""
    total_q = await db.execute(
        select(Concept).where(Concept.org_id == org_id)
    )
    total_concepts = len(total_q.scalars().all())
    if total_concepts < 2:
        return

    total_chunks_q = await db.execute(text(
        "SELECT COUNT(*) FROM document_chunks dc "
        "JOIN documents d ON d.id = dc.document_id "
        "WHERE d.org_id = :org_id"
    ), {"org_id": str(org_id)})
    total_chunks = total_chunks_q.scalar() or 1

    edges_q = await db.execute(
        select(ConceptCooccurrence).where(ConceptCooccurrence.org_id == org_id)
    )
    edges = edges_q.scalars().all()

    concept_freq: dict[UUID, int] = {}
    concepts_q = await db.execute(
        select(Concept.id, Concept.frequency).where(Concept.org_id == org_id)
    )
    for cid, freq in concepts_q.all():
        concept_freq[cid] = freq

    for edge in edges:
        if edge.raw_weight < MIN_COOCCURRENCE_FOR_PMI:
            edge.pmi_weight = 0.0
            continue
        freq_a = concept_freq.get(edge.concept_a_id, 1)
        freq_b = concept_freq.get(edge.concept_b_id, 1)
        p_ab = edge.raw_weight / max(total_chunks, 1)
        p_a = freq_a / max(total_chunks, 1)
        p_b = freq_b / max(total_chunks, 1)
        if p_a * p_b > 0:
            edge.pmi_weight = max(0.0, math.log(p_ab / (p_a * p_b)))
        else:
            edge.pmi_weight = 0.0

    await db.flush()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/documents/concepts.py
git commit -m "feat: add NLP concept extraction service with spaCy and PMI weighting"
```

---

## Task 6: Community Detection Service

**Files:**
- Create: `backend/app/services/documents/communities.py`

- [ ] **Step 1: Create the community detection module**

Create `backend/app/services/documents/communities.py`:

```python
"""Leiden community detection over concept co-occurrence graphs."""

import logging
from uuid import UUID

import igraph
import leidenalg
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    ChunkCommunity,
    Community,
    Concept,
    ConceptCooccurrence,
)

logger = logging.getLogger(__name__)

LEIDEN_RESOLUTION = 1.0
LEIDEN_SEED = 0xDEADBEEF
LEIDEN_MAX_COMM_SIZE = 10
LEIDEN_N_ITERATIONS = -1


async def detect_communities(org_id: UUID, db: AsyncSession) -> list[UUID]:
    """Run Leiden community detection on an org's concept graph.

    Replaces all existing communities for the org.
    Returns list of new community IDs.
    """
    concepts_q = await db.execute(
        select(Concept).where(Concept.org_id == org_id)
    )
    concepts = concepts_q.scalars().all()
    if len(concepts) < 2:
        return []

    concept_idx = {c.id: i for i, c in enumerate(concepts)}
    idx_to_concept = {i: c for c, i in concept_idx.items()}

    edges_q = await db.execute(
        select(ConceptCooccurrence).where(
            ConceptCooccurrence.org_id == org_id,
            ConceptCooccurrence.raw_weight >= 2,
        )
    )
    edges = edges_q.scalars().all()

    g = igraph.Graph(n=len(concepts), directed=False)
    edge_list = []
    weights = []
    for e in edges:
        a_idx = concept_idx.get(e.concept_a_id)
        b_idx = concept_idx.get(e.concept_b_id)
        if a_idx is not None and b_idx is not None:
            edge_list.append((a_idx, b_idx))
            weights.append(e.pmi_weight if e.pmi_weight and e.pmi_weight > 0 else 1.0)

    if not edge_list:
        return []

    g.add_edges(edge_list)
    g.es["weight"] = weights

    partition = leidenalg.find_partition(
        g,
        leidenalg.RBConfigurationVertexPartition,
        weights=weights,
        resolution_parameter=LEIDEN_RESOLUTION,
        n_iterations=LEIDEN_N_ITERATIONS,
        seed=LEIDEN_SEED,
        max_comm_size=LEIDEN_MAX_COMM_SIZE,
    )

    await db.execute(delete(ChunkCommunity).where(
        ChunkCommunity.community_id.in_(
            select(Community.id).where(Community.org_id == org_id)
        )
    ))
    await db.execute(delete(Community).where(Community.org_id == org_id))
    await db.flush()

    concept_names = {c.id: c.display_name or c.name for c in concepts}
    concept_freqs = {c.id: c.frequency for c in concepts}

    new_community_ids = []
    for comm_idx, members in enumerate(partition):
        if not members:
            continue

        member_concept_ids = [idx_to_concept[m] for m in members]
        sorted_by_freq = sorted(
            member_concept_ids, key=lambda cid: concept_freqs.get(cid, 0), reverse=True
        )
        top_names = [concept_names.get(cid, "?") for cid in sorted_by_freq[:5]]
        label = ", ".join(top_names)

        community = Community(
            org_id=org_id,
            level=0,
            label=label,
            member_concept_ids=[str(cid) for cid in member_concept_ids],
            metadata_json={
                "concept_count": len(member_concept_ids),
                "top_concepts": top_names,
            },
        )
        db.add(community)
        await db.flush()
        new_community_ids.append(community.id)

    await db.flush()
    return new_community_ids


async def link_chunks_to_communities(org_id: UUID, db: AsyncSession) -> None:
    """Link document chunks to communities based on concept membership."""
    communities_q = await db.execute(
        select(Community).where(Community.org_id == org_id)
    )
    communities = communities_q.scalars().all()

    concept_to_community: dict[str, UUID] = {}
    for comm in communities:
        for cid in comm.member_concept_ids:
            concept_to_community[cid] = comm.id

    from app.models.document import Document, DocumentChunk
    chunks_q = await db.execute(
        select(DocumentChunk).join(Document).where(
            Document.org_id == org_id,
            DocumentChunk.concept_ids != None,
        )
    )
    chunks = chunks_q.scalars().all()

    for chunk in chunks:
        if not chunk.concept_ids:
            continue
        seen_communities: set[UUID] = set()
        for cid in chunk.concept_ids:
            comm_id = concept_to_community.get(str(cid))
            if comm_id and comm_id not in seen_communities:
                seen_communities.add(comm_id)
                db.add(ChunkCommunity(chunk_id=chunk.id, community_id=comm_id))

    await db.flush()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/documents/communities.py
git commit -m "feat: add Leiden community detection service over concept co-occurrence graph"
```

---

## Task 7: Wire Knowledge Layer into Vectorization Pipeline

**Files:**
- Modify: `backend/app/workers/vectorization.py`

- [ ] **Step 1: Extend the Celery task to run concept extraction + community detection**

The existing file at `backend/app/workers/vectorization.py` needs to be modified. The current code (53 lines) does: parse → chunk → embed → set status. We need to add three steps after embed: concept extraction, PMI computation, and community detection.

Insert new imports inside `_run()` after the existing imports, and add the new steps after `vectorize_chunks`. Here is the complete replacement for the file:

```python
from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="documents.vectorize_document")
def vectorize_document_task(document_id: str) -> str:
    """Parse document on disk, chunk, embed, extract concepts, detect communities."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.document import Document
    from app.services.documents.parser import parse_file
    from app.services.extraction.chunker import chunk_document
    from app.services.documents.vectorizer import vectorize_chunks
    from app.services.documents.concepts import extract_and_store_concepts, compute_pmi_weights
    from app.services.documents.communities import detect_communities, link_chunks_to_communities

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    async def _run() -> None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            doc = await session.get(Document, UUID(document_id))
            if doc is None or not doc.storage_path:
                return
            doc_id_str = str(doc.id)
            elements = parse_file(doc.storage_path)
            text_chunks = chunk_document(doc_id_str, elements)
            chunks = [
                {
                    "chunk_index": c.chunk_index,
                    "content": c.text,
                    "page_number": c.page_number,
                    "section_title": c.section_title,
                    "metadata_json": {"token_count": c.token_count},
                }
                for c in text_chunks
            ]

            # Step 1-3: Embed chunks (existing)
            db_chunks = await vectorize_chunks(chunks, doc.id, session)

            # Step 4-5: NLP concept extraction + co-occurrence graph
            chunk_dicts = [
                {"content": c.get("content") or "", "chunk_db_id": db_chunks[i].id}
                for i, c in enumerate(chunks)
            ]
            concept_count = await extract_and_store_concepts(
                chunk_dicts, doc.id, doc.org_id, session
            )
            await compute_pmi_weights(doc.org_id, session)

            # Step 6-7: Community detection + chunk-community linking
            community_ids = await detect_communities(doc.org_id, session)
            if community_ids:
                await link_chunks_to_communities(doc.org_id, session)

            doc.chunk_count = len(chunks)
            doc.concept_count = concept_count
            doc.community_ids = [str(cid) for cid in community_ids]
            doc.status = "indexed"
            await session.commit()

    try:
        with langfuse_context():
            with langfuse_span("document_vectorization", metadata={"document_id": document_id}):
                asyncio.run(_run())
        return document_id
    finally:
        flush_langfuse()
```

**Key change**: `vectorize_chunks` already returns `list[DocumentChunk]` (see `backend/app/services/documents/vectorizer.py:100`), so we capture that to get `db_chunks[i].id` for concept extraction.

- [ ] **Step 2: Commit**

```bash
git add backend/app/workers/vectorization.py
git commit -m "feat: wire concept extraction and community detection into vectorization pipeline"
```

---

## Task 8: Community-Aware Retrieval

**Files:**
- Modify: `backend/app/services/processes/context.py`
- Modify: `backend/app/services/chat/context.py`

- [ ] **Step 1: Enhance `semantic_document_search` with community filtering**

In `backend/app/services/processes/context.py`, replace the existing `semantic_document_search` function (lines 215-260). The current function does flat pgvector cosine distance search. The replacement adds community filtering as a first pass, then falls back to global vector search for remaining slots.

**Important**: The return dict shape must match the existing consumers — currently `{"content", "document_id", "section_title"}`. We add `"chunk_id"` as a new field (used by provenance tracking) but keep the existing fields.

```python
async def semantic_document_search(
    org_id: UUID,
    db: AsyncSession,
    query_text: str,
    limit: int = 10,
) -> list[dict]:
    """Find document chunks via community-filtered vector search, with global fallback."""
    from app.services.ai.router import get_embedding_provider
    from app.services.documents.vectorizer import _embed

    client = get_embedding_provider()
    if client is None:
        logger.warning("no_embedding_provider org_id=%s", org_id)
        return await gather_document_chunks_for_domain(org_id, db, query_text, limit)

    try:
        query_embedding = await _embed(client, query_text)
    except Exception as exc:
        logger.error("embedding_failed org_id=%s error=%s", org_id, exc)
        return await gather_document_chunks_for_domain(org_id, db, query_text, limit)

    docs_q = await db.execute(
        select(Document.id).where(Document.org_id == org_id, Document.status == "indexed")
    )
    doc_ids = [row[0] for row in docs_q.all()]
    if not doc_ids:
        return []

    base_query = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
    )

    # Community filtering: extract concepts from query, find matching communities
    community_chunk_ids: set | None = None
    try:
        from app.services.documents.concepts import extract_noun_phrases
        from app.models.knowledge import Concept, Community, ChunkCommunity

        query_phrases = extract_noun_phrases(query_text)
        query_concepts = {canonical for canonical, _ in query_phrases}

        if query_concepts:
            communities_q = await db.execute(
                select(Community).where(Community.org_id == org_id)
            )
            relevant_comm_ids = []
            for comm in communities_q.scalars().all():
                if not comm.member_concept_ids:
                    continue
                concept_names_q = await db.execute(
                    select(Concept.name).where(
                        Concept.id.in_([UUID(c) for c in comm.member_concept_ids if c])
                    )
                )
                comm_names = {r[0] for r in concept_names_q.all()}
                if query_concepts & comm_names:
                    relevant_comm_ids.append(comm.id)

            if relevant_comm_ids:
                cc_q = await db.execute(
                    select(ChunkCommunity.chunk_id).where(
                        ChunkCommunity.community_id.in_(relevant_comm_ids)
                    )
                )
                community_chunk_ids = {row[0] for row in cc_q.all()}
    except Exception:
        logger.warning("community_filter_failed, falling back to global", exc_info=True)

    if community_chunk_ids:
        comm_q = await db.execute(
            base_query.where(DocumentChunk.id.in_(community_chunk_ids)).limit(limit)
        )
        community_chunks = list(comm_q.scalars().all())
        remaining = limit - len(community_chunks)
        if remaining > 0:
            seen = {c.id for c in community_chunks}
            global_q = await db.execute(base_query.limit(limit + len(seen)))
            extras = [c for c in global_q.scalars().all() if c.id not in seen][:remaining]
            all_chunks = community_chunks + extras
        else:
            all_chunks = community_chunks
    else:
        q = await db.execute(base_query.limit(limit))
        all_chunks = list(q.scalars().all())

    return [
        {
            "content": c.content or "",
            "document_id": str(c.document_id),
            "section_title": c.section_title,
            "chunk_id": str(c.id),
        }
        for c in all_chunks
    ]
```

Add `from uuid import UUID` to the top of the file if not already present (it's already there since the function signatures use `UUID`).

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/processes/context.py
git commit -m "feat: add community-aware retrieval to semantic document search"
```

---

## Task 9: Pydantic Schemas + API Endpoints for Knowledge Layer

**Files:**
- Create: `backend/app/schemas/knowledge.py`
- Modify: `backend/app/api/routes/documents.py`

- [ ] **Step 1: Create knowledge schemas**

Create `backend/app/schemas/knowledge.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConceptResponse(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    concept_type: str
    frequency: int

    model_config = {"from_attributes": True}


class CommunityResponse(BaseModel):
    id: UUID
    label: str | None
    level: int
    member_concept_ids: list[str]
    metadata_json: dict

    model_config = {"from_attributes": True}


class ProvenanceResponse(BaseModel):
    id: UUID
    process_id: UUID
    document_id: UUID
    chunk_ids: list[str]
    relevance_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Add community and provenance endpoints to documents router**

Add to `backend/app/api/routes/documents.py`:

```python
from app.models.knowledge import Community, ProcessDocumentSource
from app.schemas.knowledge import CommunityResponse, ProvenanceResponse


@router.get("/{document_id}/communities", response_model=list[CommunityResponse])
async def get_document_communities(
    document_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> list[CommunityResponse]:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.community_ids:
        return []
    comm_ids = [UUID(cid) for cid in doc.community_ids]
    q = await db.execute(select(Community).where(Community.id.in_(comm_ids)))
    return [CommunityResponse.model_validate(c) for c in q.scalars().all()]


@router.get("/{document_id}/provenance", response_model=list[ProvenanceResponse])
async def get_document_provenance(
    document_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> list[ProvenanceResponse]:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")
    q = await db.execute(
        select(ProcessDocumentSource).where(ProcessDocumentSource.document_id == document_id)
    )
    return [ProvenanceResponse.model_validate(p) for p in q.scalars().all()]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/knowledge.py backend/app/api/routes/documents.py
git commit -m "feat: add knowledge layer schemas and community/provenance API endpoints"
```

---

## Task 10: Amendment Notifications Service

**Files:**
- Create: `backend/app/services/documents/notifications.py`

- [ ] **Step 1: Create the notification module**

Create `backend/app/services/documents/notifications.py`:

```python
"""Identify processes affected by a newly indexed document."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Community, ProcessDocumentSource
from app.models.process import BusinessProcess

logger = logging.getLogger(__name__)


async def find_affected_processes(
    document_id: UUID,
    org_id: UUID,
    community_ids: list[UUID],
    db: AsyncSession,
) -> list[dict]:
    """Find business processes that may be affected by a new document.

    Uses community overlap: processes linked (via provenance) to chunks
    in the same communities as the new document's chunks.
    """
    if not community_ids:
        return []

    existing_sources_q = await db.execute(
        select(ProcessDocumentSource.process_id).distinct().where(
            ProcessDocumentSource.document_id != document_id,
        )
    )
    process_ids_with_sources = {row[0] for row in existing_sources_q.all()}
    if not process_ids_with_sources:
        return []

    affected = []
    for pid in process_ids_with_sources:
        source_q = await db.execute(
            select(ProcessDocumentSource).where(
                ProcessDocumentSource.process_id == pid,
            )
        )
        sources = source_q.scalars().all()
        for src in sources:
            src_doc_q = await db.execute(
                select(Community.id).where(
                    Community.org_id == org_id,
                    Community.id.in_(community_ids),
                )
            )
            overlapping = src_doc_q.scalars().all()
            if overlapping:
                process = await db.get(BusinessProcess, pid)
                if process:
                    affected.append({
                        "process_id": str(pid),
                        "process_name": process.name,
                        "overlap_community_count": len(overlapping),
                    })
                break

    logger.info(
        "amendment_notification doc_id=%s affected_count=%d",
        document_id,
        len(affected),
    )
    return affected
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/documents/notifications.py
git commit -m "feat: add amendment notification service for affected process detection"
```

---

## Task 11: Frontend — Fix API Client + Add Knowledge Types

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Fix the upload path and add knowledge API methods**

In `frontend/src/api/client.ts`, line 185, change the upload path from `'/documents'` to `'/documents/upload'`:

```typescript
      return request<Document>('/documents/upload', { method: 'POST', body })
```

Add new API methods after the existing `delete` method (line 198) in the documents section, before the closing `},`:

```typescript
    communities: (documentId: string) =>
      request<Community[]>(`/documents/${documentId}/communities`),
    provenance: (documentId: string) =>
      request<ProvenanceLink[]>(`/documents/${documentId}/provenance`),
```

Also add `Community` and `ProvenanceLink` to the type imports at the top of the file (line 1-30).

- [ ] **Step 2: Add knowledge types to frontend types**

Add to `frontend/src/types/index.ts`:

```typescript
export interface Community {
  id: string
  label: string | null
  level: number
  member_concept_ids: string[]
  metadata_json: Record<string, unknown>
}

export interface ProvenanceLink {
  id: string
  process_id: string
  document_id: string
  chunk_ids: string[]
  relevance_score: number | null
  created_at: string
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/types/index.ts
git commit -m "fix: correct document upload API path and add knowledge layer types"
```

---

## Task 12: Frontend — Smart Document Library Page

**Files:**
- Create: `frontend/src/pages/Documents/index.tsx`
- Create: `frontend/src/pages/Documents/UploadZone.tsx`
- Create: `frontend/src/pages/Documents/DocumentDetail.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppLayout.tsx`

This task creates the full Documents page. Due to the size, implementation will follow existing page patterns (see `frontend/src/pages/Processes/index.tsx` and `frontend/src/pages/Organization/index.tsx` for style conventions).

- [ ] **Step 1: Create the UploadZone component**

Create `frontend/src/pages/Documents/UploadZone.tsx` — a drag-and-drop upload area that accepts multiple files, shows per-file progress, calls `api.documents.upload()` for each file, and invokes an `onUploadComplete` callback when all files finish. Use Tailwind for styling — dashed border dropzone that highlights on drag-over, file list with progress bars, error states per file.

- [ ] **Step 2: Create the DocumentDetail component**

Create `frontend/src/pages/Documents/DocumentDetail.tsx` — a slide-over panel (similar to existing patterns) that shows: filename, status badge, file size, upload date, uploader, mime type, chunk count, concept count, tags (editable), communities list (fetched via `api.documents.communities(id)`), provenance links (fetched via `api.documents.provenance(id)`), and a delete button.

- [ ] **Step 3: Create the Documents page**

Create `frontend/src/pages/Documents/index.tsx` — the main page with:
- `UploadZone` at the top
- Search input (filters by filename client-side, with debounced server semantic search)
- Paginated table of documents with columns: filename, status (color-coded badge), size (formatted), upload date, topics (community labels as pills), chunk count, tags
- Row click opens `DocumentDetail` slide-over
- Bulk select checkboxes for bulk delete/tag
- Uses TanStack Query for data fetching with polling (refetch every 5s to catch status changes from background vectorization)

- [ ] **Step 4: Add the route and nav link**

In `frontend/src/App.tsx`, add inside the `<Route element={<AppLayout />}>` block:

```tsx
<Route path="/documents" element={<DocumentsPage />} />
```

Add the import at the top:

```tsx
import DocumentsPage from './pages/Documents'
```

In `frontend/src/components/AppLayout.tsx`, add a "Documents" entry to the `nav` array (line 16-22). Place it after "Processes":

```typescript
const nav = [
  { to: '/analysis', label: 'Analysis' },
  { to: '/organization', label: 'Organization' },
  { to: '/processes', label: 'Processes' },
  { to: '/documents', label: 'Documents' },
  { to: '/recommendations', label: 'Recommendations' },
  { to: '/agents', label: 'Agents' },
]
```

Note: The existing nav uses simple `{to, label}` objects with no icons — follow this pattern.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Documents/ frontend/src/App.tsx frontend/src/components/AppLayout.tsx
git commit -m "feat: add Smart Document Library page with upload, list, detail, and search"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] Content hashing & dedup (Task 3)
- [x] NLP concept extraction (Task 5)
- [x] Community detection (Task 6)
- [x] Community-aware retrieval (Task 8)
- [x] Provenance tracking (Task 1 model, Task 9 API)
- [x] Incremental amendment notifications (Task 10)
- [x] Enhanced delete with disk cleanup (Task 4)
- [x] Smart Document Library UI (Task 12)
- [x] Fix API path mismatch (Task 11)
- [x] Embedding model version tracking (Task 1, stored on Document)
- [x] Database migration (Task 1)
- [x] Dependencies (Task 2)

**2. Placeholder scan:** All tasks contain actual code or specific instructions. Task 12 steps 1-3 describe UI components at design level rather than full JSX because frontend components depend on the exact Tailwind patterns used in the existing codebase (which vary by page). The implementing agent should reference `frontend/src/pages/Processes/index.tsx` for table patterns and `frontend/src/pages/Organization/index.tsx` for form/panel patterns.

**3. Type consistency:** `extract_and_store_concepts` takes `list[dict]` with `content` and `chunk_db_id` keys — this matches what Task 7 passes. `detect_communities` returns `list[UUID]` — Task 7 stores these as `doc.community_ids`. API schemas match model field names.
