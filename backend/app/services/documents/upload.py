"""Handle multipart uploads with content hashing, dedup, and S3 storage."""

import hashlib
import uuid
from pathlib import PurePosixPath
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.documents.storage import make_s3_key, upload_to_bucket


async def handle_upload(
    file: UploadFile,
    org_id: UUID,
    user_id: UUID | None,
    db: AsyncSession,
) -> tuple[Document, bool]:
    """Read upload into memory, hash, dedup, store in S3 bucket.

    Returns (document, is_new). If is_new is False, the returned document
    is an existing duplicate and nothing was uploaded.
    """
    safe_name = PurePosixPath(file.filename or "unnamed").name
    doc_id = uuid.uuid4()

    sha256 = hashlib.sha256()
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
        sha256.update(chunk)

    file_bytes = b"".join(chunks)
    size = len(file_bytes)
    content_hash = sha256.hexdigest()

    existing = await db.scalar(
        select(Document).where(
            Document.org_id == org_id,
            Document.content_hash == content_hash,
            Document.status == "indexed",
        )
    )
    if existing:
        return existing, False

    s3_key = make_s3_key(org_id, doc_id, safe_name)
    upload_to_bucket(s3_key, file_bytes, content_type=file.content_type)

    from app.core.config import get_settings
    settings = get_settings()

    doc = Document(
        id=doc_id,
        org_id=org_id,
        filename=safe_name,
        mime_type=file.content_type,
        file_size_bytes=size,
        storage_path=s3_key,
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
