"""Salesforce record count telemetry."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataObject, RecordTelemetry


async def poll_record_counts(connection_id: UUID, db: AsyncSession) -> int:
    """
    Poll Salesforce for approximate record counts per object and insert RecordTelemetry rows.

    TODO: SOQL COUNT() or Bulk API against live org using PlatformConnection credentials.
    """
    q = await db.execute(
        select(MetadataObject).where(MetadataObject.connection_id == connection_id)
    )
    objects = q.scalars().all()
    now = datetime.now(tz=UTC)
    for obj in objects:
        db.add(
            RecordTelemetry(
                object_id=obj.id,
                record_count=obj.record_count,
                created_count_delta=0,
                modified_count_delta=0,
                snapshot_at=now,
            )
        )
    await db.flush()
    return len(objects)


async def calculate_velocity(object_id: UUID, timeframe_days: int, db: AsyncSession) -> float:
    """
    Compute velocity score from telemetry deltas over the timeframe window.
    """
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
    return float(created_sum + modified_sum)
