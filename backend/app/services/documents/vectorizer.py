"""Embeddings and vector search over document chunks."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.services.ai.router import get_embedding_provider


async def vectorize_chunks(
    chunks: list[dict],
    document_id: UUID,
    db: AsyncSession,
) -> list[DocumentChunk]:
    """
    Embed chunk texts and persist DocumentChunk rows with pgvector embeddings.
    """
    provider = get_embedding_provider()
    out: list[DocumentChunk] = []
    for c in chunks:
        content = c.get("content") or ""
        embedding = await provider.embed(content) if content.strip() else [0.0] * 3072
        row = DocumentChunk(
            document_id=document_id,
            chunk_index=int(c["chunk_index"]),
            content=content,
            embedding=embedding,
            page_number=c.get("page_number"),
            section_title=c.get("section_title"),
            metadata_json=c.get("metadata_json") or {},
        )
        db.add(row)
        out.append(row)
    await db.flush()
    return out


async def search_documents(
    query: str,
    org_id: UUID,
    top_k: int,
    db: AsyncSession,
) -> list[dict]:
    """
    Semantic search using cosine distance against stored embeddings for the org.

    Returns dict rows suitable for DocumentSearchResult schema mapping.
    """
    provider = get_embedding_provider()
    qvec = await provider.embed(query)
    vec_str = "[" + ",".join(str(float(x)) for x in qvec) + "]"
    sql = text(
        """
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            dc.chunk_index,
            dc.content,
            dc.page_number,
            dc.section_title,
            (dc.embedding <=> CAST(:qvec AS vector)) AS distance
        FROM document_chunks dc
        INNER JOIN documents d ON d.id = dc.document_id
        WHERE d.org_id = CAST(:org_id AS uuid)
          AND dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> CAST(:qvec AS vector)
        LIMIT :limit
        """
    )
    result = await db.execute(
        sql, {"qvec": vec_str, "org_id": str(org_id), "limit": top_k}
    )
    rows: list[dict] = []
    for r in result.mappings().all():
        dist = float(r["distance"])
        score = float(1.0 / (1.0 + dist))
        rows.append(
            {
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "page_number": r["page_number"],
                "section_title": r["section_title"],
                "score": score,
            }
        )
    return rows
