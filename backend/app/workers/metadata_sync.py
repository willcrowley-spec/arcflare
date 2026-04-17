import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.connection import PlatformConnection
    from app.services.classification import run_classification
    from app.services.salesforce.metadata import sync_metadata
    from app.services.sync_progress import (
        complete_progress,
        get_redis_client,
        init_progress,
        update_phase,
    )

    r = get_redis_client()
    init_progress(connection_id, r)

    def progress_cb(conn_id: str, phase: str, status: str, count: int = 0) -> None:
        update_phase(conn_id, phase, status, count, r)

    async def _run_sync() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn:
                conn.status = "syncing"
                await session.commit()
            return await sync_metadata(UUID(connection_id), session, progress_callback=progress_cb)

    async def _run_classification() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn is None:
                return 0
            count = await run_classification(conn.org_id, session, connection_id=UUID(connection_id))
            await session.commit()
            return count

    async def _run_vectorize() -> int:
        from app.services.metadata_vectorizer import vectorize_org_metadata

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn is None:
                return 0
            return await vectorize_org_metadata(UUID(connection_id), conn.org_id, session)

    async def _mark_connected() -> None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn:
                conn.status = "connected"
                await session.commit()

    try:
        asyncio.run(_run_sync())

        update_phase(connection_id, "classification", "pulling", 0, r)
        try:
            count = asyncio.run(_run_classification())
            update_phase(connection_id, "classification", "done", count, r)
        except Exception as ce:
            logger.warning("classification_failed connection=%s error=%s", connection_id, ce)
            update_phase(connection_id, "classification", "done", 0, r)

        update_phase(connection_id, "vectorization", "pulling", 0, r)
        try:
            count = asyncio.run(_run_vectorize())
            update_phase(connection_id, "vectorization", "done", count, r)
        except Exception as ve:
            logger.warning("vectorization_failed connection=%s error=%s", connection_id, ve)
            update_phase(connection_id, "vectorization", "done", 0, r)

        complete_progress(connection_id, r=r)
    except Exception as exc:
        complete_progress(connection_id, error=str(exc), r=r)
        raise

    asyncio.run(_mark_connected())
    return connection_id
