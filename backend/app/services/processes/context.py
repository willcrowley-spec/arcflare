"""Build LLM context from org intelligence, metadata, and documents."""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from app.models.document import Document, DocumentChunk
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataDependency,
    MetadataField,
    MetadataObject,
)
from app.models.organization import Organization

logger = logging.getLogger(__name__)


async def gather_org_context(org_id: UUID, db: AsyncSession) -> dict:
    """Organization intelligence: industry, business model, enrichment data."""
    org = await db.get(Organization, org_id)
    if org is None:
        return {}
    settings = org.settings_json or {}
    return {
        "name": org.name,
        "industry": settings.get("industry", "Unknown"),
        "business_model": settings.get("business_model", ""),
        "description": settings.get("description", ""),
        "domains": settings.get("domains", []),
        "employee_count": settings.get("employee_count"),
        "enrichment": settings.get("enrichment", {}),
    }


async def gather_metadata_summary(org_id: UUID, db: AsyncSession) -> dict:
    """High-level metadata summary for Pass 1 — only objects with data, no field-level detail."""
    objects_q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.record_count > 0,
        ).order_by(MetadataObject.record_count.desc())
    )
    objects = objects_q.scalars().all()

    automations_q = await db.execute(
        select(MetadataAutomation).where(MetadataAutomation.org_id == org_id)
    )
    automations = automations_q.scalars().all()

    components_q = await db.execute(
        select(MetadataComponent).where(MetadataComponent.org_id == org_id)
    )
    components = components_q.scalars().all()

    return {
        "objects": [
            {
                "api_name": o.api_name,
                "label": o.label,
                "record_count": o.record_count,
                "is_custom": o.is_custom,
                "classification": o.classification,
                "field_count": o.field_count,
            }
            for o in objects
        ],
        "automations": [
            {
                "api_name": a.api_name,
                "label": a.label,
                "type": a.automation_type,
                "related_object": a.related_object or "",
            }
            for a in automations
        ],
        "components": [
            {
                "api_name": c.api_name,
                "label": c.label,
                "category": c.component_category,
            }
            for c in components
        ],
        "totals": {
            "objects_with_data": len(objects),
            "automations": len(automations),
            "components": len(components),
        },
    }


async def gather_metadata_for_domain(
    org_id: UUID,
    db: AsyncSession,
    object_names: list[str],
    automation_names: list[str],
) -> dict:
    """Full metadata detail — includes fields, relationships, record types.

    Returns empty collections when both name lists are empty rather than
    loading the entire org (which explodes prompt size and DB load).
    """
    if not object_names and not automation_names:
        return {"objects": [], "automations": []}

    obj_details = []
    if object_names:
        objects_q = await db.execute(
            select(MetadataObject).where(
                MetadataObject.org_id == org_id,
                MetadataObject.api_name.in_(object_names),
            )
        )
        objects = objects_q.scalars().all()

        obj_ids = [o.id for o in objects]
        fields_by_obj: dict[UUID, list] = {oid: [] for oid in obj_ids}
        if obj_ids:
            fields_q = await db.execute(
                select(MetadataField).where(
                    MetadataField.object_id.in_(obj_ids),
                ).limit(50 * len(obj_ids))
            )
            for f in fields_q.scalars().all():
                bucket = fields_by_obj.get(f.object_id)
                if bucket is not None and len(bucket) < 50:
                    bucket.append(f)

        for o in objects:
            fields = fields_by_obj.get(o.id, [])
            obj_details.append(
                {
                    "api_name": o.api_name,
                    "label": o.label,
                    "record_count": o.record_count,
                    "classification": o.classification,
                    "record_types": (o.metadata_json or {}).get("record_types", []),
                    "relationships": [
                        {"api_name": f.api_name, "target": f.relationship_to, "type": f.relationship_type}
                        for f in fields
                        if f.relationship_to
                    ],
                    "fields": [
                        {
                            "api_name": f.api_name,
                            "label": f.label,
                            "type": f.field_type,
                            "is_custom": f.is_custom,
                            "is_required": f.is_required,
                            "description": (f.metadata_json or {}).get("description", ""),
                        }
                        for f in fields
                    ],
                }
            )

    auto_list = []
    if automation_names:
        auto_q = await db.execute(
            select(MetadataAutomation).where(
                MetadataAutomation.org_id == org_id,
                MetadataAutomation.api_name.in_(automation_names),
            )
        )
        auto_list = [
            {
                "api_name": a.api_name,
                "label": a.label,
                "type": a.automation_type,
                "description": (a.metadata_json or {}).get("description", ""),
                "is_active": (a.metadata_json or {}).get("is_active", True),
            }
            for a in auto_q.scalars().all()
        ]

    return {"objects": obj_details, "automations": auto_list}


async def gather_document_summary(org_id: UUID, db: AsyncSession) -> list[dict]:
    """Document titles for Pass 1."""
    docs_q = await db.execute(
        select(Document).where(Document.org_id == org_id, Document.status == "indexed")
    )
    docs = docs_q.scalars().all()
    return [
        {"id": str(d.id), "filename": d.filename, "chunk_count": d.chunk_count or 0}
        for d in docs
    ]


async def gather_document_chunks_for_domain(
    org_id: UUID,
    db: AsyncSession,
    domain_description: str,
    limit: int = 20,
) -> list[dict]:
    """Return document chunks for context. Simple query for now — will add vector search later."""
    docs_q = await db.execute(
        select(Document.id).where(Document.org_id == org_id, Document.status == "indexed")
    )
    doc_ids = [row[0] for row in docs_q.all()]
    if not doc_ids:
        return []

    chunks_q = await db.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.content.isnot(None),
        ).limit(limit)
    )
    chunks = chunks_q.scalars().all()
    return [
        {"content": c.content or "", "document_id": str(c.document_id)}
        for c in chunks
    ]


async def batch_semantic_search(
    org_id: UUID,
    db: AsyncSession,
    queries: list[str],
    limit: int = 10,
) -> list[list[dict]]:
    """Batch-embed multiple queries and run vector search for each.

    Returns one result list per query, in the same order as the input.
    Falls back to sequential calls on embedding failure.
    """
    if not queries:
        return []

    from app.services.ai.router import get_embedding_provider
    from app.services.documents.vectorizer import _embed_batch

    client = get_embedding_provider()

    try:
        embeddings = await _embed_batch(client, queries)
    except Exception as exc:
        logger.error("batch_embedding_failed org_id=%s error=%s", org_id, exc)
        return [
            await gather_document_chunks_for_domain(org_id, db, q, limit)
            for q in queries
        ]

    docs_q = await db.execute(
        select(Document.id).where(Document.org_id == org_id, Document.status == "indexed")
    )
    doc_ids = [row[0] for row in docs_q.all()]
    if not doc_ids:
        return [[] for _ in queries]

    results: list[list[dict]] = []
    for emb in embeddings:
        q = await db.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id.in_(doc_ids),
                DocumentChunk.embedding.isnot(None),
            )
            .order_by(DocumentChunk.embedding.cosine_distance(emb))
            .limit(limit)
        )
        chunks = list(q.scalars().all())
        results.append([
            {
                "content": c.content or "",
                "document_id": str(c.document_id),
                "section_title": c.section_title,
                "chunk_id": str(c.id),
            }
            for c in chunks
        ])
    return results


async def semantic_document_search(
    org_id: UUID,
    db: AsyncSession,
    query_text: str,
    limit: int = 10,
) -> list[dict]:
    """Find document chunks via summary-boosted vector search.

    Uses community summary embeddings to identify thematically relevant
    communities, then boosts chunks from those communities in the global
    cosine-distance ranking.  Cross-cutting queries still get global results;
    community-aligned chunks rank higher.
    """
    from app.services.ai.router import get_embedding_provider
    from app.services.documents.vectorizer import _embed

    client = get_embedding_provider()

    try:
        query_embedding = await _embed(client, query_text)
    except Exception as exc:
        logger.error("embedding_failed org_id=%s error=%s", org_id, exc)
        return await gather_document_chunks_for_domain(org_id, db, query_text, limit)

    docs_q = await db.execute(
        select(Document.id).where(Document.org_id == org_id, Document.status == "indexed")
    )
    doc_ids = [row[0] for row in docs_q.all()]
    if not doc_ids:
        return []

    base_query = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
    )

    boosted_chunk_ids: set = set()
    try:
        from app.models.knowledge import Community, ChunkCommunity

        top_comms_q = await db.execute(
            select(Community.id)
            .where(
                Community.org_id == org_id,
                Community.source == "document",
                Community.summary_embedding.isnot(None),
            )
            .order_by(Community.summary_embedding.cosine_distance(query_embedding))
            .limit(3)
        )
        top_comm_ids = [row[0] for row in top_comms_q.all()]

        if top_comm_ids:
            cc_q = await db.execute(
                select(ChunkCommunity.chunk_id).where(
                    ChunkCommunity.community_id.in_(top_comm_ids)
                )
            )
            boosted_chunk_ids = {row[0] for row in cc_q.all()}
    except Exception:
        logger.warning("community_boost_failed, falling back to global", exc_info=True)

    if boosted_chunk_ids:
        boost_slots = max(1, limit // 2)
        global_slots = limit - boost_slots

        comm_q = await db.execute(
            base_query.where(DocumentChunk.id.in_(boosted_chunk_ids)).limit(boost_slots)
        )
        boosted_chunks = list(comm_q.scalars().all())
        seen = {c.id for c in boosted_chunks}

        global_q = await db.execute(base_query.limit(limit + len(seen)))
        global_chunks = [c for c in global_q.scalars().all() if c.id not in seen]
        all_chunks = boosted_chunks + global_chunks[: limit - len(boosted_chunks)]
    else:
        q = await db.execute(base_query.limit(limit))
        all_chunks = list(q.scalars().all())

    return [
        {
            "content": c.content or "",
            "document_id": str(c.document_id),
            "section_title": c.section_title,
            "chunk_id": str(c.id),
        }
        for c in all_chunks
    ]


async def gather_metadata_relationships(
    org_id: UUID,
    db: AsyncSession,
    object_names: list[str],
) -> dict:
    """Lookup/master-detail relationships and automation trigger chains between objects."""
    if not object_names:
        return {"relationships": [], "automations": []}

    obj_ids_q = await db.execute(
        select(MetadataObject.id).where(
            MetadataObject.org_id == org_id,
            MetadataObject.api_name.in_(object_names),
        )
    )
    obj_ids = [row[0] for row in obj_ids_q.all()]

    if not obj_ids:
        return {"relationships": [], "automations": []}

    fields_q = await db.execute(
        select(MetadataField).where(
            MetadataField.object_id.in_(obj_ids),
            MetadataField.relationship_to.isnot(None),
        )
    )
    relationships = []
    for f in fields_q.scalars().all():
        relationships.append(
            {
                "field": f.api_name,
                "target_object": f.relationship_to,
                "type": f.relationship_type or "Lookup",
            }
        )

    autos_q = await db.execute(
        select(MetadataAutomation).where(
            MetadataAutomation.org_id == org_id,
            MetadataAutomation.related_object.in_(object_names),
        )
    )
    automations = [
        {
            "name": a.api_name,
            "type": a.automation_type,
            "trigger_object": a.related_object,
            "details": a.metadata_json or {},
        }
        for a in autos_q.scalars().all()
    ]

    return {"relationships": relationships, "automations": automations}


async def gather_dependency_subgraph(
    org_id: UUID,
    db: AsyncSession,
    object_names: list[str],
    max_edges: int = 200,
) -> list[dict]:
    """Return dependency graph edges touching the given object set (1-hop).

    Scoped to edges where either source or target api_name is in the object
    set so prompt token budget stays bounded.
    """
    if not object_names:
        return []

    edges_q = await db.execute(
        select(MetadataDependency).where(
            MetadataDependency.org_id == org_id,
            sa.or_(
                MetadataDependency.source_api_name.in_(object_names),
                MetadataDependency.target_api_name.in_(object_names),
            ),
        ).limit(max_edges)
    )
    return [
        {
            "source": e.source_api_name,
            "source_type": e.source_type,
            "relationship": e.relationship_type,
            "target": e.target_api_name,
            "target_type": e.target_type,
            "metadata": e.metadata_json or {},
        }
        for e in edges_q.scalars().all()
    ]


async def get_relevant_metadata_summaries(
    org_id: UUID,
    db: AsyncSession,
    query_text: str,
    limit: int = 5,
) -> list[dict]:
    """Find metadata community summaries most relevant to the query.

    Returns top-K metadata communities ranked by summary embedding similarity.
    Each dict contains: id, label, summary, member_count, members (top node IDs).
    """
    from app.services.ai.router import get_embedding_provider
    from app.services.documents.vectorizer import _embed
    from app.models.knowledge import Community

    try:
        client = get_embedding_provider()
        query_embedding = await _embed(client, query_text)
    except Exception as exc:
        logger.error("metadata_summary_embed_failed org_id=%s error=%s", org_id, exc)
        return []

    comms_q = await db.execute(
        select(Community)
        .where(
            Community.org_id == org_id,
            Community.source == "metadata",
            Community.summary_embedding.isnot(None),
        )
        .order_by(Community.summary_embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    return [
        {
            "id": str(c.id),
            "label": c.label,
            "summary": c.summary,
            "member_count": (c.metadata_json or {}).get("member_count", 0),
            "members": (c.member_concept_ids or [])[:15],
        }
        for c in comms_q.scalars().all()
    ]
