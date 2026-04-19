from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentOrg, CurrentUserDep, DbSession
from app.models.document import Document
from app.models.organization import User
from app.schemas.common import PaginatedResponse
from app.schemas.document import (
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
    await db.delete(doc)
    await db.commit()
