"""Build LLM context from org intelligence, metadata, and documents."""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataField, MetadataObject
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
    """Full metadata detail for Pass 2 — includes fields, relationships, record types."""
    objects_q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.api_name.in_(object_names) if object_names else MetadataObject.org_id == org_id,
        )
    )
    objects = objects_q.scalars().all()

    obj_details = []
    for o in objects:
        fields_result = await db.execute(
            select(MetadataField).where(MetadataField.object_id == o.id).limit(50)
        )
        fields = fields_result.scalars().all()

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

    auto_q = await db.execute(
        select(MetadataAutomation).where(
            MetadataAutomation.org_id == org_id,
            MetadataAutomation.api_name.in_(automation_names)
            if automation_names
            else MetadataAutomation.org_id == org_id,
        )
    )
    autos = auto_q.scalars().all()

    return {
        "objects": obj_details,
        "automations": [
            {
                "api_name": a.api_name,
                "label": a.label,
                "type": a.automation_type,
                "description": (a.metadata_json or {}).get("description", ""),
                "is_active": (a.metadata_json or {}).get("is_active", True),
            }
            for a in autos
        ],
    }


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
