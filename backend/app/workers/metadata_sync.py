from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    """Enqueue async metadata sync for a Salesforce connection."""
    # Import inside task to avoid circular imports at worker boot.
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.services.salesforce.metadata import sync_metadata

    async def _run() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # sync_metadata commits the session after persisting.
            return await sync_metadata(UUID(connection_id), session)

    asyncio.run(_run())
    return connection_id
