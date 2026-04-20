from uuid import UUID

from app.workers.celery_app import celery_app


_DOC_SUMMARY_PROMPT = """\
You are a business analyst. Summarize this document in 2-4 sentences.
Focus on: what business processes, policies, or procedures it describes,
who the key actors are, and what systems or tools are mentioned.
Be specific — name processes, teams, and systems rather than being generic.

<document>
{text}
</document>"""


@celery_app.task(name="documents.vectorize_document")
def vectorize_document_task(document_id: str) -> str:
    """Download document from S3, parse, chunk, embed, extract concepts, summarize."""
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
    from app.services.documents.concepts import extract_and_store_concepts
    from app.services.ai.router import llm_call

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    async def _set_phase(session, doc, phase: str) -> None:
        doc.processing_phase = phase
        await session.commit()

    async def _run() -> None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            doc = await session.get(Document, UUID(document_id))
            if doc is None or not doc.storage_path:
                return

            doc.status = "processing"
            await _set_phase(session, doc, "downloading")

            file_bytes = download_from_bucket(doc.storage_path)
            suffix = Path(doc.filename).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            try:
                tmp.write(file_bytes)
                tmp.close()

                await _set_phase(session, doc, "parsing")
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

                full_doc_text = "\n".join(c.text for c in text_chunks if c.text)

                await _set_phase(session, doc, "embedding")
                db_chunks = await vectorize_chunks(
                    chunks, doc.id, session,
                    full_document_text=full_doc_text,
                )

                await _set_phase(session, doc, "extracting concepts")
                chunk_dicts = [
                    {"content": c.get("content") or "", "chunk_db_id": db_chunks[i].id}
                    for i, c in enumerate(chunks)
                ]
                concept_count = await extract_and_store_concepts(
                    chunk_dicts, doc.id, doc.org_id, session
                )

                await _set_phase(session, doc, "summarizing")
                summary = None
                try:
                    summary_text = full_doc_text[:12000]
                    result = await asyncio.to_thread(
                        llm_call,
                        prompt=_DOC_SUMMARY_PROMPT.format(text=summary_text),
                        max_tokens=400,
                        tier="lite",
                        operation="community_summarization",
                    )
                    summary = result.text.strip()
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning(
                        "doc_summary_failed doc_id=%s", document_id, exc_info=True,
                    )

                doc.chunk_count = len(chunks)
                doc.concept_count = concept_count
                doc.summary = summary
                doc.processing_phase = None
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
