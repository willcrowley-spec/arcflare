"""Object classification and velocity scoring."""
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataObject, RecordTelemetry
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


async def compute_velocity_for_object(
    object_id: UUID,
    window_days: int,
    db: AsyncSession,
) -> float:
    since = datetime.now(tz=UTC) - timedelta(days=window_days)
    q = await db.execute(
        select(
            func.coalesce(func.sum(RecordTelemetry.created_count_delta), 0),
            func.coalesce(func.sum(RecordTelemetry.modified_count_delta), 0),
        ).where(
            RecordTelemetry.object_id == object_id,
            RecordTelemetry.snapshot_at >= since,
        )
    )
    created_sum, modified_sum = q.one()
    return float((created_sum or 0) + (modified_sum or 0))


def classify_object(record_count: int, velocity_score: float, threshold: float) -> str:
    if record_count == 0:
        return "empty"
    if velocity_score > threshold:
        return "operational"
    return "configuration"


async def run_classification(
    org_id: UUID,
    db: AsyncSession,
    connection_id: UUID | None = None,
) -> int:
    """Compute velocity and classification for all auto-classified objects in an org."""
    org = await db.get(Organization, org_id)
    if org is None:
        return 0
    config = _get_config(org)
    window = config["velocity_window_days"]
    threshold = config["classification_threshold"]

    filters = [
        MetadataObject.org_id == org_id,
        MetadataObject.classification_source != "manual",
    ]
    if connection_id:
        filters.append(MetadataObject.connection_id == connection_id)

    result = await db.execute(select(MetadataObject).where(*filters))
    objects = result.scalars().all()

    count = 0
    for obj in objects:
        velocity = await compute_velocity_for_object(obj.id, window, db)
        obj.velocity_score = velocity
        obj.classification = classify_object(obj.record_count, velocity, threshold)
        count += 1

    await db.flush()
    logger.info("classification_complete org=%s objects=%d", org_id, count)
    return count


async def reanalyze_org(org_id: UUID, db: AsyncSession) -> int:
    """Re-run classification using current config. Does NOT re-sync or re-vectorize."""
    count = await run_classification(org_id, db)
    await db.commit()
    return count
