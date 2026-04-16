"""Mine business processes from metadata and documents."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def mine_from_metadata(org_id: UUID, db: AsyncSession) -> list[dict]:
    """
    Derive candidate processes from Salesforce metadata patterns.

    TODO: cluster objects/flows into process candidates using heuristics + LLM.
    """
    return []


async def mine_from_documents(org_id: UUID, db: AsyncSession) -> list[dict]:
    """
    Derive candidate processes from ingested document corpus.

    TODO: RAG summarization over DocumentChunk content.
    """
    return []
