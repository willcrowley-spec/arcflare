import logging
from uuid import UUID, uuid4

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="metadata.sync_metadata")
def sync_metadata_task(connection_id: str) -> str:
    import asyncio

    async def _pipeline() -> tuple[str, str | None]:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine as _create_engine

        from app.core.config import get_settings
        from app.models.connection import PlatformConnection
        from app.services.classification import run_classification
        from app.services.metadata_graph import build_dependency_graph, detect_metadata_communities
        from app.services.metadata_vectorizer import vectorize_org_metadata
        from app.services.salesforce.metadata import sync_metadata
        from app.services.sync_event_log import SyncEventEmitter

        _settings = get_settings()
        _engine = _create_engine(
            _settings.DATABASE_URL,
            pool_pre_ping=True,
        )
        factory = async_sessionmaker(_engine, expire_on_commit=False)
        run_id = uuid4()
        org_id: UUID | None = None

        async def _set_status(status: str) -> None:
            async with factory() as s:
                conn = await s.get(PlatformConnection, UUID(connection_id))
                if conn:
                    conn.status = status
                    await s.commit()

        try:
            async with factory() as session:
                conn = await session.get(PlatformConnection, UUID(connection_id))
                org_id_str = str(conn.org_id) if conn else None
                org_id = conn.org_id if conn else None

            if not org_id:
                raise ValueError(f"Connection {connection_id} not found")

            await _set_status("syncing")

            async with factory() as session:
                emitter = SyncEventEmitter(
                    UUID(connection_id), org_id, run_id, session,
                )
                await emitter.purge_old_runs()
                await emitter.emit("run_start", "Metadata sync started")
                await sync_metadata(
                    UUID(connection_id), session,
                    event_emitter=emitter,
                )
                await session.commit()

            try:
                async with factory() as session:
                    emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                    await emitter.emit("phase_start", "Building dependency graph...", phase="graph_build")
                    conn_obj = await session.get(PlatformConnection, UUID(connection_id))
                    if conn_obj:
                        edge_count = await build_dependency_graph(UUID(connection_id), conn_obj.org_id, session)
                        await detect_metadata_communities(UUID(connection_id), conn_obj.org_id, session)
                    else:
                        edge_count = 0
                    await emitter.emit(
                        "phase_complete",
                        f"Dependency graph complete — {edge_count} edges",
                        phase="graph_build",
                        detail={"edge_count": edge_count},
                    )
                    await session.commit()
            except Exception:
                logger.exception("graph_build_failed connection=%s", connection_id)

            try:
                async with factory() as session:
                    emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                    await emitter.emit("phase_start", "Classifying metadata...", phase="classification")
                    conn_obj = await session.get(PlatformConnection, UUID(connection_id))
                    if conn_obj:
                        count = await run_classification(conn_obj.org_id, session, connection_id=UUID(connection_id))
                    else:
                        count = 0
                    await emitter.emit(
                        "phase_complete",
                        f"Classification complete — {count} objects classified",
                        phase="classification",
                        detail={"classified_count": count},
                    )
                    await session.commit()
            except Exception:
                logger.exception("classification_failed connection=%s", connection_id)

            try:
                async with factory() as session:
                    emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                    await emitter.emit("phase_start", "Vectorizing metadata...", phase="vectorization")
                    conn_obj = await session.get(PlatformConnection, UUID(connection_id))
                    if conn_obj:
                        count = await vectorize_org_metadata(UUID(connection_id), conn_obj.org_id, session)
                    else:
                        count = 0
                    await emitter.emit(
                        "phase_complete",
                        f"Vectorization complete — {count} chunks",
                        phase="vectorization",
                        detail={"chunk_count": count},
                    )
                    await session.commit()
            except Exception:
                logger.exception("vectorization_failed connection=%s", connection_id)

            async with factory() as session:
                emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                await emitter.emit("run_complete", "Sync complete")
                await session.commit()

            await _set_status("connected")
            return connection_id, org_id_str

        except Exception as exc:
            logger.exception("sync_task_failed connection=%s", connection_id)
            try:
                if org_id is not None:
                    async with factory() as session:
                        emitter = SyncEventEmitter(UUID(connection_id), org_id, run_id, session)
                        await emitter.emit("error", f"Sync failed: {exc}", severity="error")
                        await session.commit()
                else:
                    logger.error(
                        "cannot_emit_sync_error_event_missing_org connection=%s",
                        connection_id,
                    )
            except Exception:
                logger.exception("failed_to_emit_error_event connection=%s", connection_id)
            try:
                await _set_status("error")
            except Exception:
                logger.exception("failed_to_set_error_status connection=%s", connection_id)
            raise
        finally:
            await _engine.dispose()

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    try:
        with langfuse_context(org_id=connection_id):
            with langfuse_span("metadata_sync", metadata={"connection_id": connection_id}):
                result_id, org_id_str = asyncio.run(_pipeline())
        return result_id
    finally:
        flush_langfuse()
