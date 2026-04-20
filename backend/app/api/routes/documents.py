from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentOrg, CurrentUserDep, DbSession
from app.models.document import Document, DocumentChunk
from app.models.knowledge import Community, Concept, ProcessDocumentSource
from app.models.organization import User
from app.schemas.knowledge import CommunityResponse, ProvenanceResponse
from app.schemas.common import PaginatedResponse
from app.schemas.document import (
    DocumentChunkResponse,
    DocumentConceptResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResult,
    DocumentUploadResponse,
)
from app.services.documents.upload import handle_upload
from app.services.documents.vectorizer import search_documents
from app.workers.vectorization import vectorize_document_task

router = APIRouter()


class TagsPatch(BaseModel):
    tags: list[str] = Field(default_factory=list)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    res = await db.execute(select(User).where(User.clerk_user_id == user.clerk_user_id))
    db_user = res.scalar_one_or_none()
    user_id = db_user.id if db_user else None
    doc, is_new = await handle_upload(file, org.id, user_id, db)
    await db.commit()
    if is_new:
        vectorize_document_task.delay(str(doc.id))
    return DocumentUploadResponse.model_validate(doc)


@router.get("/", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    db: DbSession,
    org: CurrentOrg,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedResponse[DocumentResponse]:
    total = await db.scalar(
        select(func.count()).select_from(Document).where(Document.org_id == org.id)
    )
    total = int(total or 0)
    q = await db.execute(
        select(Document)
        .where(Document.org_id == org.id)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = q.scalars().all()
    items = [DocumentResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> DocumentResponse:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.patch("/{document_id}/tags", response_model=DocumentResponse)
async def patch_document_tags(
    document_id: UUID,
    body: TagsPatch,
    db: DbSession,
    org: CurrentOrg,
) -> DocumentResponse:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.tags = body.tags
    await db.commit()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)


@router.post("/search", response_model=list[DocumentSearchResult])
async def search_docs(
    body: DocumentSearchRequest,
    db: DbSession,
    org: CurrentOrg,
) -> list[DocumentSearchResult]:
    rows = await search_documents(body.query, org.id, body.top_k, db)
    return [
        DocumentSearchResult(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            score=r["score"],
            page_number=r["page_number"],
            section_title=r["section_title"],
        )
        for r in rows
    ]


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
        from app.services.documents.storage import delete_from_bucket

        delete_from_bucket(doc.storage_path)

    await db.delete(doc)
    await db.commit()


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
async def get_document_chunks(
    document_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> list[DocumentChunkResponse]:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")
    q = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return [DocumentChunkResponse.model_validate(c) for c in q.scalars().all()]


@router.get("/{document_id}/concepts", response_model=list[DocumentConceptResponse])
async def get_document_concepts(
    document_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> list[DocumentConceptResponse]:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Document not found")
    q = await db.execute(
        select(DocumentChunk.concept_ids).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.concept_ids.isnot(None),
        )
    )
    concept_ids: set[str] = set()
    for row in q.all():
        concept_ids.update(row[0] or [])
    if not concept_ids:
        return []
    concept_uuids = [UUID(cid) for cid in concept_ids]
    cq = await db.execute(
        select(Concept).where(Concept.id.in_(concept_uuids)).order_by(Concept.frequency.desc()).limit(50)
    )
    return [
        DocumentConceptResponse(
            id=c.id, name=c.name, display_name=c.display_name, frequency=c.frequency,
        )
        for c in cq.scalars().all()
    ]


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
    q = await db.execute(select(Community).where(Community.id.in_(comm_ids), Community.org_id == org.id))
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
