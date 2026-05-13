"""Phase 6: Vectorize the org research profile into pgvector.

Creates a synthetic Document from the assembled profile and runs it through
the existing vectorize_chunks pipeline, making the research profile searchable
alongside metadata and uploaded documents in the discovery pipeline.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.services.documents.vectorizer import vectorize_chunks

logger = logging.getLogger(__name__)

SYNTHETIC_MIME = "application/x-org-research"


def _profile_to_chunks(profile: dict, company_name: str) -> list[dict]:
    """Convert the structured profile into text chunks for embedding."""
    chunks: list[dict] = []
    idx = 0

    overview = profile.get("overview", {})
    summary = profile.get("company_summary", "")
    if summary:
        chunks.append({
            "chunk_index": idx,
            "content": f"Company Overview: {company_name}\n\n{summary}",
            "section_title": f"Org Research: {company_name} Overview",
            "metadata_json": {"source": "org_research", "type": "overview"},
        })
        idx += 1

    for key in ("industry", "headquarters", "founded"):
        val = overview.get(key)
        if val:
            chunks.append({
                "chunk_index": idx,
                "content": f"{company_name} — {key.title()}: {val}",
                "section_title": f"Org Research: {key.title()}",
                "metadata_json": {"source": "org_research", "type": "overview", "field": key},
            })
            idx += 1

    size = profile.get("size_and_scale", {})
    size_lines = []
    for field in ("employee_range", "revenue_range", "funding_stage", "total_funding"):
        val = size.get(field)
        if val:
            size_lines.append(f"{field.replace('_', ' ').title()}: {val}")
    growth = size.get("growth_signals", [])
    if growth:
        size_lines.append("Growth Signals: " + "; ".join(growth))
    if size_lines:
        chunks.append({
            "chunk_index": idx,
            "content": f"{company_name} — Size & Scale\n" + "\n".join(size_lines),
            "section_title": "Org Research: Size & Scale",
            "metadata_json": {"source": "org_research", "type": "size"},
        })
        idx += 1

    products = profile.get("products_and_services", [])
    if products:
        product_lines = [f"- {p.get('name', '')}: {p.get('description', '')}" for p in products[:8]]
        chunks.append({
            "chunk_index": idx,
            "content": f"{company_name} — Products & Services\n" + "\n".join(product_lines),
            "section_title": "Org Research: Products & Services",
            "metadata_json": {"source": "org_research", "type": "products"},
        })
        idx += 1

    icp = profile.get("ideal_customer_profile", {})
    if isinstance(icp, dict) and (icp.get("segments") or icp.get("buyer_personas")):
        icp_lines = []
        if icp.get("segments"):
            icp_lines.append("Target Segments: " + ", ".join(icp["segments"]))
        if icp.get("buyer_personas"):
            icp_lines.append("Buyer Personas: " + ", ".join(icp["buyer_personas"]))
        if icp.get("value_propositions"):
            icp_lines.append("Value Propositions: " + "; ".join(icp["value_propositions"]))
        if icp.get("competitive_positioning"):
            icp_lines.append(f"Positioning: {icp['competitive_positioning']}")
        chunks.append({
            "chunk_index": idx,
            "content": f"{company_name} — Ideal Customer Profile\n" + "\n".join(icp_lines),
            "section_title": "Org Research: ICP",
            "metadata_json": {"source": "org_research", "type": "icp"},
        })
        idx += 1

    structure = profile.get("corporate_structure", {})
    if isinstance(structure, dict):
        struct_lines = []
        if structure.get("parent_company"):
            struct_lines.append(f"Parent Company: {structure['parent_company']}")
        for exec_info in structure.get("key_executives", [])[:10]:
            if isinstance(exec_info, dict):
                struct_lines.append(f"Executive: {exec_info.get('name', '')}")
            else:
                struct_lines.append(f"Executive: {exec_info}")
        deps = structure.get("departments_mentioned", [])
        if deps:
            struct_lines.append("Departments: " + ", ".join(deps))
        if struct_lines:
            chunks.append({
                "chunk_index": idx,
                "content": f"{company_name} — Corporate Structure\n" + "\n".join(struct_lines),
                "section_title": "Org Research: Corporate Structure",
                "metadata_json": {"source": "org_research", "type": "structure"},
            })
            idx += 1

    tech = profile.get("technology_stack", {})
    if isinstance(tech, dict):
        tech_items = tech.get("mentioned_technologies", [])
        integrations = tech.get("integrations", [])
        if tech_items or integrations:
            tech_lines = []
            if tech_items:
                tech_lines.append("Technologies: " + ", ".join(tech_items[:15]))
            if integrations:
                tech_lines.append("Integrations: " + ", ".join(integrations[:10]))
            chunks.append({
                "chunk_index": idx,
                "content": f"{company_name} — Technology Stack\n" + "\n".join(tech_lines),
                "section_title": "Org Research: Technology",
                "metadata_json": {"source": "org_research", "type": "technology"},
            })
            idx += 1

    fin = profile.get("financial_drivers", {})
    if isinstance(fin, dict):
        fin_lines = []
        for field in ("business_model", "pricing_model"):
            val = fin.get(field)
            if val:
                fin_lines.append(f"{field.replace('_', ' ').title()}: {val}")
        indicators = fin.get("growth_indicators", [])
        if indicators:
            fin_lines.append("Growth Indicators: " + "; ".join(str(i) for i in indicators))
        if fin_lines:
            chunks.append({
                "chunk_index": idx,
                "content": f"{company_name} — Financial Drivers\n" + "\n".join(fin_lines),
                "section_title": "Org Research: Financials",
                "metadata_json": {"source": "org_research", "type": "financials"},
            })
            idx += 1

    return chunks


async def vectorize_research_profile(
    org_id: UUID,
    profile: dict,
    company_name: str,
    db: AsyncSession,
    *,
    auto_commit: bool = False,
) -> int:
    """Create a synthetic document from the research profile and vectorize it.

    Follows the same pattern as vectorize_org_metadata: creates a Document with
    a synthetic mime type, generates text chunks, and embeds them.
    """
    sync_filename = f"org-research-{org_id}.txt"

    existing = await db.execute(
        select(Document).where(
            Document.org_id == org_id,
            Document.mime_type == SYNTHETIC_MIME,
            Document.filename == sync_filename,
        )
    )
    old_docs = existing.scalars().all()
    for old_doc in old_docs:
        await db.execute(
            DocumentChunk.__table__.delete().where(DocumentChunk.document_id == old_doc.id)
        )
        await db.delete(old_doc)
    if old_docs:
        await db.flush()

    chunks = _profile_to_chunks(profile, company_name)
    if not chunks:
        logger.warning("vectorize_research_empty org=%s", org_id)
        return 0

    doc = Document(
        org_id=org_id,
        filename=sync_filename,
        mime_type=SYNTHETIC_MIME,
        status="indexed",
        tags=["org_research"],
        chunk_count=len(chunks),
        summary=profile.get("company_summary", "")[:500] or None,
    )
    db.add(doc)
    await db.flush()

    await vectorize_chunks(chunks, doc.id, db, skip_contextual=True)
    if auto_commit:
        await db.commit()

    logger.info(
        "vectorize_research_complete org=%s chunks=%d",
        org_id, len(chunks),
    )
    return len(chunks)
