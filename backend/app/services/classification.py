"""Object classification and velocity scoring."""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataObject
from app.models.organization import Organization

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "velocity_window_days": 30,
    "classification_threshold": 0.1,
    "min_records_for_vectorization": 1,
}


def _get_config(org: Organization) -> dict:
    config = org.analysis_config or {}
    return {**DEFAULT_CONFIG, **config}


def classify_object(record_count: int, velocity_score: float, threshold: float) -> str:
    if record_count == 0:
        return "empty"
    ratio = velocity_score / record_count if record_count > 0 else 0.0
    if ratio > threshold:
        return "operational"
    return "configuration"


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
    config = _get_config(org)
    threshold = config["classification_threshold"]

    filters = [
        MetadataObject.org_id == org_id,
        MetadataObject.classification_source != "manual",
    ]
    if connection_id:
        filters.append(MetadataObject.connection_id == connection_id)

    result = await db.execute(select(MetadataObject).where(*filters))
    objects = result.scalars().all()

    counts = {"operational": 0, "configuration": 0, "empty": 0}
    for obj in objects:
        obj.classification = classify_object(obj.record_count, obj.velocity_score, threshold)
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
