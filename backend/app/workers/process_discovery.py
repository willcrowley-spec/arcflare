"""Celery task for process discovery pipeline."""
import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PHASES = [
    "context_gathering",
    "domain_discovery",
    "domain_decomposition",
    "cross_domain_synthesis",
    "graph_generation",
]


def _map_discovery_status(status: str) -> str:
    if status in ("gathering", "running"):
        return "pulling"
    return status


@celery_app.task(name="processes.discover")
def process_discovery_task(org_id: str) -> str:
    import asyncio

    from app.core.observability import flush_langfuse
    from app.services.sync_progress import get_redis_client

    r = get_redis_client()
    run_key = f"discovery:{org_id}"

    for phase in PHASES:
        r.hset(run_key, f"phase:{phase}:status", "waiting")
        r.hset(run_key, f"phase:{phase}:count", "0")
        r.hset(run_key, f"phase:{phase}:total", "0")
    r.hset(run_key, "status", "running")
    r.hset(run_key, "run_id", "")
    r.expire(run_key, 3600)

    def _update(phase: str, status: str, count: int = 0, total: int = 0) -> None:
        r.hset(run_key, f"phase:{phase}:status", status)
        r.hset(run_key, f"phase:{phase}:count", str(count))
        r.hset(run_key, f"phase:{phase}:total", str(total))

    def _discovery_progress_cb(phase: str, status: str, count: int, total: int) -> None:
        redis_phase = {
            "domain_discovery": "domain_discovery",
            "domain_decomposition": "domain_decomposition",
            "cross_domain": "cross_domain_synthesis",
        }.get(phase)
        if redis_phase:
            _update(redis_phase, _map_discovery_status(status), count, total)

    async def _pipeline() -> str:
        from datetime import datetime, timezone

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.discovery import DiscoveryRun
        from app.services.processes.discovery import (
            cleanup_previous_run,
            run_pass1,
            run_pass2,
            run_pass3,
        )

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with factory() as session:
                from app.models.organization import Organization

                org = await session.get(Organization, UUID(org_id))
                org_config = (org.analysis_config or {}) if org else {}

                run = DiscoveryRun(org_id=UUID(org_id), status="running")
                session.add(run)
                await session.flush()
                run_id = run.id
                r.hset(run_key, "run_id", str(run_id))

                try:
                    _update("context_gathering", "pulling")
                    await cleanup_previous_run(UUID(org_id), session)
                    await session.commit()
                    _update("context_gathering", "done")

                    _update("domain_discovery", "pulling", 0, 1)
                    domains = await run_pass1(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("domain_discovery", "done", len(domains), max(len(domains), 1))

                    _update("domain_decomposition", "pulling", 0, max(len(domains), 1))
                    process_count = await run_pass2(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("domain_decomposition", "done", process_count, max(process_count, 1))

                    _update("cross_domain_synthesis", "pulling", 0, 1)
                    synthesis = await run_pass3(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("cross_domain_synthesis", "done", 1, 1)

                    _update("graph_generation", "pulling")
                    _update("graph_generation", "done")

                    run.status = "completed"
                    run.completed_at = datetime.now(tz=timezone.utc)
                    run.pass_results = {
                        "domains": len(domains),
                        "processes": process_count,
                        "executive_summary": synthesis.get("executive_summary", ""),
                    }
                    await session.commit()

                    r.hset(run_key, "status", "completed")
                    logger.info(
                        "discovery_complete org=%s run=%s domains=%d processes=%d",
                        org_id,
                        run_id,
                        len(domains),
                        process_count,
                    )
                    return str(run_id)

                except Exception as exc:
                    logger.exception("discovery_failed org=%s", org_id)
                    try:
                        await session.rollback()
                    except Exception:
                        logger.exception("discovery_rollback_failed org=%s", org_id)
                    try:
                        run.status = "failed"
                        run.error = str(exc)[:2000]
                        run.completed_at = datetime.now(tz=timezone.utc)
                        await session.commit()
                    except Exception:
                        logger.exception("failed_to_update_run_status org=%s", org_id)
                    r.hset(run_key, "status", "failed")
                    r.hset(run_key, "error", str(exc)[:500])
                    raise
        finally:
            await engine.dispose()

    from app.core.observability import langfuse_span

    try:
        with langfuse_span("process_discovery", metadata={"org_id": org_id}):
            return asyncio.run(_pipeline())
    finally:
        flush_langfuse()
