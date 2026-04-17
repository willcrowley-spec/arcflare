"""Mine business processes — delegates to the discovery pipeline."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def mine_from_metadata(org_id: UUID, db: AsyncSession) -> list[dict]:
    """Legacy stub — process discovery now handled by the three-pass pipeline."""
    return []


async def mine_from_documents(org_id: UUID, db: AsyncSession) -> list[dict]:
    """Legacy stub — document analysis now handled by the three-pass pipeline."""
    return []
