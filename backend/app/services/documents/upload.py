"""Handle multipart uploads and persist Document rows."""

import uuid
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def handle_upload(
    file: UploadFile,
    org_id: UUID,
    user_id: UUID | None,
    db: AsyncSession,
    upload_root: str = "uploads",
) -> Document:
    """
    Stream upload to disk under upload_root/org_id and create Document record.
    """
    safe_name = Path(file.filename or "unnamed").name
    doc_id = uuid.uuid4()
    dest_dir = Path(upload_root) / str(org_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{doc_id}_{safe_name}"

    size = 0
    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

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
    )
    db.add(doc)
    await db.flush()
    return doc
