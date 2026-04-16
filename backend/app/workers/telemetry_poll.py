from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="telemetry.poll_telemetry")
def poll_telemetry_task(connection_id: str) -> str:
    """Poll Salesforce for record counts and persist telemetry snapshots."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.services.salesforce.telemetry import poll_record_counts

    async def _run() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # poll_record_counts commits after inserting telemetry rows.
            return await poll_record_counts(UUID(connection_id), session)

    asyncio.run(_run())
    return connection_id
