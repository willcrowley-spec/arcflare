"""Embeddings and vector search over document chunks using Gemini."""
import asyncio
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import DocumentChunk
from app.services.ai.router import get_embedding_provider

logger = logging.getLogger(__name__)


def _embed_model() -> str:
    return get_settings().EMBEDDING_MODEL


def _embed_dims() -> int:
    return get_settings().EMBEDDING_DIMS


async def _embed(client, content: str) -> list[float]:
    from app.core.observability import langfuse_generation

    model = _embed_model()
    dims = _embed_dims()

    with langfuse_generation(
        name="embedding",
        model=model,
        input=content[:200],
        metadata={"dimensions": dims, "input_length": len(content)},
    ) as gen:
        def _sync() -> list[float]:
            result = client.models.embed_content(
                model=model,
                contents=content,
                config={"output_dimensionality": dims},
            )
            return list(result.embeddings[0].values)

        vectors = await asyncio.to_thread(_sync)

        if gen is not None:
            try:
                gen.update(usage={"total": 1})
            except Exception:
                pass

    return vectors


async def _embed_batch(client, texts: list[str]) -> list[list[float]]:
    from app.core.observability import langfuse_generation

    model = _embed_model()
    dims = _embed_dims()

    with langfuse_generation(
        name="embedding_batch",
        model=model,
        input=f"[{len(texts)} texts]",
        metadata={"dimensions": dims, "batch_size": len(texts)},
    ) as gen:
        def _sync() -> list[list[float]]:
            result = client.models.embed_content(
                model=model,
                contents=texts,
                config={"output_dimensionality": dims},
            )
            return [list(e.values) for e in result.embeddings]

        vectors = await asyncio.to_thread(_sync)

        if gen is not None:
            try:
                gen.update(usage={"total": len(texts)})
            except Exception:
                pass

    return vectors


async def vectorize_chunks(
    chunks: list[dict],
    document_id: UUID,
    db: AsyncSession,
) -> list[DocumentChunk]:
    provider = get_embedding_provider()
    out: list[DocumentChunk] = []

    batch_texts = []
    batch_indices = []
    for i, c in enumerate(chunks):
        content = c.get("content") or ""
        if content.strip():
            batch_texts.append(content)
            batch_indices.append(i)

    embeddings_map: dict[int, list[float]] = {}
    for batch_start in range(0, len(batch_texts), 100):
        batch_slice = batch_texts[batch_start:batch_start + 100]
        batch_idx_slice = batch_indices[batch_start:batch_start + 100]
        try:
            vectors = await _embed_batch(provider, batch_slice)
            for idx, vec in zip(batch_idx_slice, vectors):
                embeddings_map[idx] = vec
        except Exception:
            logger.warning("batch_embed_failed, falling back to individual")
            for idx, txt in zip(batch_idx_slice, batch_slice):
                try:
                    embeddings_map[idx] = await _embed(provider, txt)
                except Exception as e:
                    logger.warning("embed_failed chunk=%d error=%s", idx, e)
                    embeddings_map[idx] = [0.0] * _embed_dims()

    dims = _embed_dims()
    for i, c in enumerate(chunks):
        content = c.get("content") or ""
        embedding = embeddings_map.get(i, [0.0] * dims)
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
    provider = get_embedding_provider()
    qvec = await _embed(provider, query)
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
