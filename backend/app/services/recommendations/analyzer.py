"""Analyze org-wide signals to detect improvement patterns."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import PlatformConnection
from app.models.metadata import MetadataObject
async def analyze_org(org_id: UUID, db: AsyncSession) -> dict:
    """
    Aggregate metadata and connection health into pattern features.

    Returns a dict consumed by the scorer.
    """
    conn_count = await db.scalar(
        select(func.count()).select_from(PlatformConnection).where(
            PlatformConnection.org_id == org_id
        )
    )
    obj_count = await db.scalar(
        select(func.count()).select_from(MetadataObject).where(MetadataObject.org_id == org_id)
    )
    custom_objects = await db.scalar(
        select(func.count()).select_from(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.is_custom.is_(True),
        )
    )
    return {
        "org_id": str(org_id),
        "connection_count": int(conn_count or 0),
        "metadata_object_count": int(obj_count or 0),
        "custom_object_count": int(custom_objects or 0),
    }
