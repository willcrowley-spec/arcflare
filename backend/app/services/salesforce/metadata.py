"""Salesforce metadata sync and describe operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import PlatformConnection


async def sync_metadata(connection_id: UUID, db: AsyncSession) -> int:
    """
    Pull global and per-object describe data from Salesforce and persist MetadataObject rows.

    TODO: Call Salesforce REST /services/data/vXX.0/sobjects with stored OAuth token.
    """
    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise ValueError("Connection not found")

    # Placeholder: mark sync time; real impl would upsert objects from API.
    from datetime import UTC, datetime

    conn.last_sync_at = datetime.now(tz=UTC)
    await db.flush()
    return 0


async def describe_global(connection: PlatformConnection) -> dict:
    """
    Return global describe for the connected org.

    TODO: GET {instance_url}/services/data/vXX.0/sobjects with Bearer token.
    """
    return {"sobjects": [], "connection_id": str(connection.id)}


async def describe_object(connection: PlatformConnection, object_name: str) -> dict:
    """
    Describe a single SObject including fields.

    TODO: GET {instance_url}/services/data/vXX.0/sobjects/{name}/describe
    """
    return {"name": object_name, "fields": [], "connection_id": str(connection.id)}
