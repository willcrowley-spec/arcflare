"""Celery task for process discovery pipeline (v2: evidence-grounded)."""
import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PHASES = [
    "context_gathering",
    "domain_discovery",
    "evidence_assembly",
    "extraction",
    "verification",
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

    def _progress_cb(phase: str, status: str, count: int, total: int) -> None:
        mapped = {
            "domain_discovery": "domain_discovery",
            "evidence_assembly": "evidence_assembly",
            "extraction": "extraction",
            "verification": "verification",
            "cross_domain_synthesis": "cross_domain_synthesis",
        }.get(phase)
        if mapped:
            _update(mapped, _map_discovery_status(status), count, total)

    async def _pipeline() -> str:
        from datetime import datetime, timezone

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.discovery import DiscoveryRun
        from app.services.processes.discovery import (
            cleanup_previous_run,
            run_v2_phase1,
            run_v2_phase2,
            run_v2_phase3,
            run_v2_phase4,
            run_v2_phase5,
            run_v2_persist,
            run_v2_quality_scoring,
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

                    # Phase 1: Domain Discovery
                    _update("domain_discovery", "pulling", 0, 1)
                    domains, org_ctx = await run_v2_phase1(
                        UUID(org_id), run_id, session,
                        progress_cb=_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("domain_discovery", "done", len(domains), max(len(domains), 1))

                    # Phase 2: Evidence Assembly (no LLM)
                    _update("evidence_assembly", "pulling", 0, len(domains))
                    bundles = await run_v2_phase2(
                        UUID(org_id), session, domains,
                        progress_cb=_progress_cb,
                    )
                    _update("evidence_assembly", "done", len(bundles), len(bundles))

                    # Phase 3: Per-Domain Extraction (parallel)
                    _update("extraction", "pulling", 0, len(domains))
                    extraction_results = await run_v2_phase3(
                        UUID(org_id), run_id, session, domains, bundles,
                        progress_cb=_progress_cb,
                        model_config=org_config,
                        concurrency=settings.PROCESS_DISCOVERY_DOMAIN_CONCURRENCY,
                    )
                    _update("extraction", "done", len(extraction_results), len(extraction_results))

                    # Phase 4: Evidence Verification (parallel)
                    _update("verification", "pulling", 0, len(domains))
                    verified_results = await run_v2_phase4(
                        UUID(org_id), session, extraction_results, bundles,
                        progress_cb=_progress_cb,
                        model_config=org_config,
                        concurrency=settings.PROCESS_DISCOVERY_DOMAIN_CONCURRENCY,
                    )
                    _update("verification", "done", len(verified_results), len(verified_results))

                    # Persist extraction results
                    process_count = await run_v2_persist(
                        UUID(org_id), run_id, session, verified_results, bundles,
                    )
                    await session.commit()

                    # Phase 5: Cross-Domain Synthesis
                    _update("cross_domain_synthesis", "pulling", 0, 1)
                    synthesis = await run_v2_phase5(
                        UUID(org_id), run_id, session, org_ctx,
                        verified_results, bundles,
                        progress_cb=_progress_cb, model_config=org_config,
                    )
                    await session.commit()
                    _update("cross_domain_synthesis", "done", 1, 1)

                    # Phase 6: Quality Scoring
                    _update("quality_scoring", "pulling", 0, 1)
                    quality = await run_v2_quality_scoring(UUID(org_id), run_id, session)
                    await session.commit()
                    _update("quality_scoring", "done", 1, 1)

                    # Phase 7: Graph Generation
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
                        "executive_summary": synthesis.get("executive_summary", ""),
                        "evidence_coverage": quality.get("evidence_coverage", 0),
                    }
                    run.stage_results = {
                        "v2_domains": len(domains),
                        "v2_bundles": len(bundles),
                        "v2_processes": process_count,
                        "v2_handoffs": len(synthesis.get("cross_domain_handoffs", [])),
                        "v2_quality": quality,
                        "v2_domain_concurrency": settings.PROCESS_DISCOVERY_DOMAIN_CONCURRENCY,
                    }
                    await session.commit()

                    r.hset(run_key, "status", "completed")
                    logger.info(
                        "v2_discovery_complete org=%s run=%s domains=%d processes=%d evidence_coverage=%.2f",
                        org_id, run_id, len(domains), process_count,
                        quality.get("evidence_coverage", 0),
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
            with langfuse_span("process_discovery_v2", metadata={"org_id": org_id}):
                return asyncio.run(_pipeline())
    finally:
        flush_langfuse()
