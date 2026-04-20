"""Object classification: binary include/exclude based on record count."""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataObject
from app.models.organization import Organization

logger = logging.getLogger(__name__)


def classify_object(record_count: int) -> str:
    if record_count == 0:
        return "excluded"
    return "included"


async def run_classification(
    org_id: UUID,
    db: AsyncSession,
    connection_id: UUID | None = None,
) -> int:
    """Classify all auto-classified objects using pre-computed velocity_score."""
    org = await db.get(Organization, org_id)
    if org is None:
        logger.warning("classification_skipped org=%s reason=org_not_found", org_id)
        return 0
    filters = [
        MetadataObject.org_id == org_id,
        MetadataObject.classification_source != "manual",
    ]
    if connection_id:
        filters.append(MetadataObject.connection_id == connection_id)

    result = await db.execute(select(MetadataObject).where(*filters))
    objects = result.scalars().all()

    counts = {"included": 0, "excluded": 0}
    for obj in objects:
        obj.classification = classify_object(obj.record_count)
        counts[obj.classification] = counts.get(obj.classification, 0) + 1

    await db.flush()
    logger.info(
        "classification_complete org=%s objects=%d distribution=%s",
        org_id, len(objects), counts,
    )
    return len(objects)


async def reanalyze_org(org_id: UUID, db: AsyncSession) -> int:
    """Re-run classification using current config. Does NOT re-sync or re-vectorize."""
    count = await run_classification(org_id, db)
    await db.commit()
    return count
