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
