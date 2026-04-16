from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="documents.vectorize_document")
def vectorize_document_task(document_id: str) -> str:
    """Parse document on disk, chunk, embed, and persist DocumentChunk rows."""
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.document import Document
    from app.services.documents.parser import parse_document
    from app.services.documents.vectorizer import vectorize_chunks

    async def _run() -> None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            doc = await session.get(Document, UUID(document_id))
            if doc is None or not doc.storage_path:
                return
            chunks = parse_document(doc.storage_path)
            await vectorize_chunks(chunks, doc.id, session)
            doc.chunk_count = len(chunks)
            doc.status = "indexed"
            await session.commit()

    asyncio.run(_run())
    return document_id
