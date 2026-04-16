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
    from app.services.documents.parser import parse_file
    from app.services.extraction.chunker import chunk_document
    from app.services.documents.vectorizer import vectorize_chunks

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
            await vectorize_chunks(chunks, doc.id, session)
            doc.chunk_count = len(chunks)
            doc.status = "indexed"
            await session.commit()

    asyncio.run(_run())
    return document_id
