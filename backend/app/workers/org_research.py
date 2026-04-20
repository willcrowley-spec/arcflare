"""Celery task for organization research pipeline."""
import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PHASES = [
    "crawl",
    "search",
    "extraction",
    "verification",
    "assembly",
    "vectorization",
]


@celery_app.task(name="org_research.research_org")
def org_research_task(org_id: str) -> str:
    import asyncio

    from app.services.sync_progress import get_redis_client

    r = get_redis_client()
    run_key = f"org_research:{org_id}"

    for phase in PHASES:
        r.hset(run_key, f"phase:{phase}:status", "waiting")
        r.hset(run_key, f"phase:{phase}:count", "0")
        r.hset(run_key, f"phase:{phase}:total", "0")
    r.hset(run_key, "status", "running")
    r.hset(run_key, "profile_id", "")
    r.expire(run_key, 3600)

    def _update(phase: str, status: str, count: int = 0, total: int = 0) -> None:
        r.hset(run_key, f"phase:{phase}:status", status)
        r.hset(run_key, f"phase:{phase}:count", str(count))
        r.hset(run_key, f"phase:{phase}:total", str(total))

    def _progress_cb(phase: str, status: str, count: int, total: int) -> None:
        _update(phase, status, count, total)

    async def _pipeline() -> str:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.organization import Organization
        from app.services.research.pipeline import run_org_research_pipeline

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with factory() as session:
                org = await session.get(Organization, UUID(org_id))
                org_config = (org.analysis_config or {}) if org else {}

                profile = await run_org_research_pipeline(
                    UUID(org_id), session,
                    progress_cb=_progress_cb,
                    model_config=org_config,
                )

                r.hset(run_key, "status", "completed")
                r.hset(run_key, "profile_id", str(profile.id))

                logger.info(
                    "org_research_complete org=%s profile=%s",
                    org_id, profile.id,
                )
                return str(profile.id)

        except Exception as exc:
            logger.exception("org_research_failed org=%s", org_id)
            r.hset(run_key, "status", "failed")
            r.hset(run_key, "error", str(exc)[:500])
            raise
        finally:
            await engine.dispose()

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("org_research", metadata={"org_id": org_id}):
                return asyncio.run(_pipeline())
    finally:
        flush_langfuse()
