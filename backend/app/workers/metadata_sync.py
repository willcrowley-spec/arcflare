import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    import asyncio

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

    async def _pipeline() -> str:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.core.database import engine
        from app.models.connection import PlatformConnection
        from app.services.classification import run_classification
        from app.services.metadata_vectorizer import vectorize_org_metadata
        from app.services.salesforce.metadata import sync_metadata

        factory = async_sessionmaker(engine, expire_on_commit=False)

        async def _set_status(status: str) -> None:
            async with factory() as s:
                conn = await s.get(PlatformConnection, UUID(connection_id))
                if conn:
                    conn.status = status
                    await s.commit()

        try:
            await _set_status("syncing")

            async with factory() as session:
                await sync_metadata(UUID(connection_id), session, progress_callback=progress_cb)

            update_phase(connection_id, "classification", "pulling", 0, r)
            try:
                async with factory() as session:
                    conn = await session.get(PlatformConnection, UUID(connection_id))
                    if conn:
                        count = await run_classification(conn.org_id, session, connection_id=UUID(connection_id))
                        await session.commit()
                    else:
                        count = 0
                update_phase(connection_id, "classification", "done", count, r)
            except Exception:
                logger.exception("classification_failed connection=%s", connection_id)
                update_phase(connection_id, "classification", "done", 0, r)

            update_phase(connection_id, "vectorization", "pulling", 0, r)
            try:
                async with factory() as session:
                    conn = await session.get(PlatformConnection, UUID(connection_id))
                    if conn:
                        count = await vectorize_org_metadata(UUID(connection_id), conn.org_id, session)
                    else:
                        count = 0
                update_phase(connection_id, "vectorization", "done", count, r)
            except Exception:
                logger.exception("vectorization_failed connection=%s", connection_id)
                update_phase(connection_id, "vectorization", "done", 0, r)

            complete_progress(connection_id, r=r)
            await _set_status("connected")
            return connection_id
        except Exception as exc:
            logger.exception("sync_task_failed connection=%s", connection_id)
            complete_progress(connection_id, error=str(exc), r=r)
            try:
                await _set_status("error")
            except Exception:
                logger.exception("failed_to_set_error_status connection=%s", connection_id)
            raise

    async def _resolve_org_id() -> str | None:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.core.database import engine
        from app.models.connection import PlatformConnection

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            conn = await session.get(PlatformConnection, UUID(connection_id))
            if conn is None:
                return None
            return str(conn.org_id)

    org_id_str = asyncio.run(_resolve_org_id())

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    try:
        with langfuse_context(org_id=org_id_str):
            with langfuse_span("metadata_sync", metadata={"connection_id": connection_id}):
                return asyncio.run(_pipeline())
    finally:
        flush_langfuse()
