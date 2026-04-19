from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="documents.vectorize_document")
def vectorize_document_task(document_id: str) -> str:
    """Download document from S3, parse, chunk, embed, extract concepts, detect communities."""
    import asyncio
    import tempfile
    from pathlib import Path

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.document import Document
    from app.services.documents.parser import parse_file
    from app.services.documents.storage import download_from_bucket
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

            file_bytes = download_from_bucket(doc.storage_path)
            suffix = Path(doc.filename).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            try:
                tmp.write(file_bytes)
                tmp.close()

                doc_id_str = str(doc.id)
                elements = parse_file(tmp.name)
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

                db_chunks = await vectorize_chunks(chunks, doc.id, session)

                chunk_dicts = [
                    {"content": c.get("content") or "", "chunk_db_id": db_chunks[i].id}
                    for i, c in enumerate(chunks)
                ]
                concept_count = await extract_and_store_concepts(
                    chunk_dicts, doc.id, doc.org_id, session
                )
                await compute_pmi_weights(doc.org_id, session)

                community_ids = await detect_communities(doc.org_id, session)
                if community_ids:
                    await link_chunks_to_communities(doc.org_id, session)

                doc.chunk_count = len(chunks)
                doc.concept_count = concept_count
                doc.community_ids = [str(cid) for cid in community_ids]
                doc.status = "indexed"
                await session.commit()
            finally:
                Path(tmp.name).unlink(missing_ok=True)

    try:
        with langfuse_context():
            with langfuse_span("document_vectorization", metadata={"document_id": document_id}):
                asyncio.run(_run())
        return document_id
    finally:
        flush_langfuse()
