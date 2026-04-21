"""Embeddings and vector search over document chunks using Gemini."""
import asyncio
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import DocumentChunk
from app.services.ai.router import get_embedding_provider, llm_call

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
                estimated_tokens = max(1, len(content) // 4)
                embedding_cost = estimated_tokens * 0.006e-6
                gen.update(
                    usage_details={"input": estimated_tokens},
                    cost_details={"input": embedding_cost, "output": 0},
                )
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
                estimated_tokens = max(1, sum(len(t) // 4 for t in texts))
                embedding_cost = estimated_tokens * 0.006e-6
                gen.update(
                    usage_details={"input": estimated_tokens},
                    cost_details={"input": embedding_cost, "output": 0},
                )
            except Exception:
                pass

    return vectors


async def generate_contextual_prefixes(
    chunks: list[dict],
    full_document_text: str,
    batch_size: int = 25,
    prompt_blocks: dict[str, str] | None = None,  # required when calling; None only for backward compat
) -> dict[int, str]:
    """Generate contextual retrieval prefixes for document chunks via LLM.

    Returns a map of chunk_index -> context_prefix string.
    Uses batched prompting to minimize LLM calls.
    """
    if not full_document_text.strip():
        return {}

    doc_text = full_document_text[:15_000]
    result: dict[int, str] = {}

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        chunk_list_lines = []
        for j, c in enumerate(batch):
            content = (c.get("content") or "")[:500]
            if content.strip():
                chunk_list_lines.append(f"Chunk {j + 1}:\n{content}")

        if not chunk_list_lines:
            continue

        template = (prompt_blocks or {}).get("instructions") or ""
        prompt = template.format(
            document_text=doc_text,
            chunk_list="\n\n".join(chunk_list_lines),
        )

        try:
            llm_result = llm_call(
                prompt=prompt,
                max_tokens=1500,
                tier="lite",
                operation="contextual_retrieval",
            )
            lines = llm_result.text.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                prefix, context = line.split(":", 1)
                try:
                    idx = int(prefix.strip()) - 1
                    global_idx = batch_start + idx
                    if 0 <= global_idx < len(chunks):
                        result[global_idx] = context.strip()
                except (ValueError, IndexError):
                    continue
        except Exception:
            logger.warning("contextual_prefix_batch_failed batch_start=%d", batch_start, exc_info=True)

    return result


async def vectorize_chunks(
    chunks: list[dict],
    document_id: UUID,
    db: AsyncSession,
    full_document_text: str = "",
    skip_contextual: bool = False,
) -> list[DocumentChunk]:
    provider = get_embedding_provider()
    model_name = _embed_model()
    out: list[DocumentChunk] = []

    context_map: dict[int, str] = {}
    if not skip_contextual and full_document_text.strip():
        try:
            context_map = await generate_contextual_prefixes(chunks, full_document_text)
            logger.info("contextual_prefixes_generated count=%d/%d", len(context_map), len(chunks))
        except Exception:
            logger.warning("contextual_prefix_generation_failed", exc_info=True)

    batch_texts = []
    batch_indices = []
    contextualized_map: dict[int, str] = {}
    for i, c in enumerate(chunks):
        content = c.get("content") or ""
        if content.strip():
            ctx_prefix = context_map.get(i, "")
            if ctx_prefix:
                contextualized = f"{ctx_prefix}\n\n{content}"
            else:
                contextualized = content
            contextualized_map[i] = contextualized
            batch_texts.append(contextualized)
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

    for i, c in enumerate(chunks):
        content = c.get("content") or ""
        embedding = embeddings_map.get(i)
        ctx_content = contextualized_map.get(i)

        row = DocumentChunk(
            document_id=document_id,
            chunk_index=int(c["chunk_index"]),
            content=content,
            contextualized_content=ctx_content if ctx_content != content else None,
            embedding=embedding,
            embedding_model=model_name if embedding else None,
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
    from app.core.observability import langfuse_generation

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
    distances: list[float] = []
    for r in result.mappings().all():
        dist = float(r["distance"])
        distances.append(dist)
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

    try:
        with langfuse_generation(
            name="retrieval_quality",
            model="vector_search",
            input=query[:200],
            metadata={
                "org_id": str(org_id),
                "top_k": top_k,
                "results_returned": len(rows),
                "distances": distances[:10],
                "min_distance": min(distances) if distances else None,
                "max_distance": max(distances) if distances else None,
            },
        ):
            pass
    except Exception:
        pass

    return rows
