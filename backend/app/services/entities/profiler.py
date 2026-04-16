"""Sync business entities from Salesforce User / hierarchy sources."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import PlatformConnection
from app.models.entity import BusinessEntity


async def sync_from_salesforce(org_id: UUID, connection_id: UUID, db: AsyncSession) -> int:
    """
    Pull Salesforce Users / roles into BusinessEntity rows.

    TODO: Query Tooling / REST for User, UserRole and map into hierarchy.
    """
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org_id:
        raise ValueError("Invalid connection for organization")
    return 0


async def build_hierarchy(org_id: UUID, db: AsyncSession) -> dict:
    """Return nested tree structure for all BusinessEntity rows in the org."""
    res = await db.execute(select(BusinessEntity).where(BusinessEntity.org_id == org_id))
    entities = res.scalars().all()
    by_parent: dict[UUID | None, list[BusinessEntity]] = {}
    for e in entities:
        by_parent.setdefault(e.parent_id, []).append(e)

    def walk(parent: UUID | None) -> list[dict]:
        nodes = []
        for ent in by_parent.get(parent, []):
            nodes.append(
                {
                    "id": ent.id,
                    "name": ent.name,
                    "entity_type": ent.entity_type,
                    "children": walk(ent.id),
                }
            )
        return nodes

    return {"roots": walk(None)}
