"""Celery task for process discovery pipeline."""
import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PHASES = [
    "context_gathering",
    "domain_discovery",
    "structural_decomposition",
    "step_enrichment",
    "flow_analysis",
    "validation",
    "cross_domain_synthesis",
    "quality_scoring",
    "graph_generation",
]


def _map_discovery_status(status: str) -> str:
    if status in ("gathering", "running"):
        return "pulling"
    return status


@celery_app.task(name="processes.discover")
def process_discovery_task(org_id: str) -> str:
    import asyncio

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
            "structural_decomposition": "structural_decomposition",
            "step_enrichment": "step_enrichment",
            "flow_analysis": "flow_analysis",
            "validation": "validation",
            "cross_domain_synthesis": "cross_domain_synthesis",
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
            run_stage1,
            run_stage2,
            run_stage3,
            run_stage4,
            run_stage5,
            run_stage6,
            run_stage7,
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
                    domains = await run_stage1(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("domain_discovery", "done", len(domains), max(len(domains), 1))

                    _update("structural_decomposition", "pulling", 0, max(len(domains), 1))
                    process_count = await run_stage2(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update(
                        "structural_decomposition", "done",
                        process_count, max(process_count, 1),
                    )

                    _update("step_enrichment", "pulling", 0, 1)
                    enriched_count = await run_stage3(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update(
                        "step_enrichment", "done",
                        enriched_count, max(enriched_count, 1),
                    )

                    _update("flow_analysis", "pulling", 0, 1)
                    handoff_count = await run_stage4(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update(
                        "flow_analysis", "done",
                        handoff_count, max(handoff_count, 1),
                    )

                    _update("validation", "pulling", 0, 1)
                    validation = await run_stage5(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    critique_n = len(validation.get("critique", []))
                    _update("validation", "done", critique_n, max(critique_n, 1))

                    _update("cross_domain_synthesis", "pulling", 0, 1)
                    synthesis = await run_stage6(
                        UUID(org_id), run_id, session,
                        progress_cb=_discovery_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("cross_domain_synthesis", "done", 1, 1)

                    _update("quality_scoring", "pulling", 0, 1)
                    quality = await run_stage7(UUID(org_id), run_id, session)
                    await session.commit()
                    _update("quality_scoring", "done", 1, 1)

                    _update("graph_generation", "pulling")
                    from app.services.processes.graph import generate_graphs_for_run
                    graph_nodes = await generate_graphs_for_run(UUID(org_id), run_id, session)
                    await session.commit()
                    _update("graph_generation", "done", graph_nodes, graph_nodes)

                    run.status = "completed"
                    run.completed_at = datetime.now(tz=timezone.utc)
                    run.pass_results = {
                        "domains": len(domains),
                        "processes": process_count,
                        "enriched_steps": enriched_count,
                        "domain_handoffs": handoff_count,
                        "validation_issues": critique_n,
                        "executive_summary": synthesis.get("executive_summary", ""),
                    }
                    run.stage_results = {
                        "stage3_enriched": enriched_count,
                        "stage4_handoffs": handoff_count,
                        "stage5_critique_count": critique_n,
                        "stage7_quality": quality,
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

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("process_discovery", metadata={"org_id": org_id}):
                return asyncio.run(_pipeline())
    finally:
        flush_langfuse()
