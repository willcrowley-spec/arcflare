"""Identify processes affected by a newly indexed document."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Community, ProcessDocumentSource
from app.models.process import BusinessProcess

logger = logging.getLogger(__name__)


async def find_affected_processes(
    document_id: UUID,
    org_id: UUID,
    community_ids: list[UUID],
    db: AsyncSession,
) -> list[dict]:
    """Find business processes that may be affected by a new document.

    Uses community overlap: processes linked (via provenance) to chunks
    in the same communities as the new document's chunks.
    """
    if not community_ids:
        return []

    existing_sources_q = await db.execute(
        select(ProcessDocumentSource.process_id).distinct().where(
            ProcessDocumentSource.document_id != document_id,
        )
    )
    process_ids_with_sources = {row[0] for row in existing_sources_q.all()}
    if not process_ids_with_sources:
        return []

    affected = []
    for pid in process_ids_with_sources:
        source_q = await db.execute(
            select(ProcessDocumentSource).where(
                ProcessDocumentSource.process_id == pid,
            )
        )
        sources = source_q.scalars().all()
        for src in sources:
            src_doc_q = await db.execute(
                select(Community.id).where(
                    Community.org_id == org_id,
                    Community.id.in_(community_ids),
                )
            )
            overlapping = src_doc_q.scalars().all()
            if overlapping:
                process = await db.get(BusinessProcess, pid)
                if process:
                    affected.append({
                        "process_id": str(pid),
                        "process_name": process.name,
                        "overlap_community_count": len(overlapping),
                    })
                break

    logger.info(
        "amendment_notification doc_id=%s affected_count=%d",
        document_id,
        len(affected),
    )
    return affected
