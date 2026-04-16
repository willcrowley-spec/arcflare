"""Salesforce telemetry -- record counts, velocity, and usage metrics."""
import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_tokens
from app.models.connection import PlatformConnection
from app.models.metadata import MetadataObject, RecordTelemetry
from app.services.salesforce.metadata import get_sf_client

logger = logging.getLogger(__name__)


async def poll_record_counts(connection_id: UUID, db: AsyncSession) -> int:
    """Query live COUNT() per object from Salesforce and snapshot into RecordTelemetry."""
    conn_result = await db.execute(select(PlatformConnection).where(PlatformConnection.id == connection_id))
    connection = conn_result.scalar_one_or_none()
    if not connection or not connection.oauth_tokens_encrypted:
        logger.warning("poll_record_counts_skip connection=%s (missing or no tokens)", connection_id)
        return 0

    tokens = json.loads(decrypt_tokens(connection.oauth_tokens_encrypted))
    sf = get_sf_client(tokens["instance_url"], tokens["access_token"])

    stmt = select(MetadataObject).where(MetadataObject.connection_id == connection_id)
    result = await db.execute(stmt)
    objects = result.scalars().all()

    now = datetime.now(tz=UTC)
    count = 0
    for obj in objects:
        current = obj.record_count
        try:
            qres = sf.query(f"SELECT COUNT() FROM {obj.api_name}")
            current = int(qres.get("totalSize", 0))
        except Exception as e:
            logger.warning("sf_count_failed object=%s error=%s", obj.api_name, e)

        prev_stmt = (
            select(RecordTelemetry)
            .where(RecordTelemetry.object_id == obj.id)
            .order_by(RecordTelemetry.snapshot_at.desc())
            .limit(1)
        )
        prev_result = await db.execute(prev_stmt)
        prev = prev_result.scalar_one_or_none()

        prev_count = prev.record_count if prev else 0
        delta = current - prev_count

        obj.record_count = current

        db.add(
            RecordTelemetry(
                object_id=obj.id,
                record_count=current,
                created_count_delta=delta,
                modified_count_delta=0,
                snapshot_at=now,
            )
        )
        count += 1

    await db.commit()
    logger.info("poll_record_counts_complete connection=%s snapshots=%d", connection_id, count)
    return count


async def calculate_velocity(object_id: UUID, timeframe_days: int, db: AsyncSession) -> float:
    """Compute velocity score from telemetry deltas over the timeframe window."""
    since = datetime.now(tz=UTC) - timedelta(days=timeframe_days)
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
