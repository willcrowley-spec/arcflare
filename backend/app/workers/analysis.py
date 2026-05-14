from __future__ import annotations

from uuid import UUID

from app.workers.celery_app import celery_app


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="recommendations.generate_recommendations")
def generate_recommendations_task(org_id: str, run_id: str | None = None) -> str:
    """Run the recommendation pipeline.

    Args:
        org_id: Organization UUID as string.
        run_id: Pre-created RecommendationRun UUID.  When provided the pipeline
            reuses that row instead of creating a new one (keeps the ID
            returned by ``POST /generate`` valid for status polling).
    """
    import asyncio

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span
    from app.services.recommendations.pipeline import run_recommendation_pipeline

    async def _run() -> str:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings

        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(_engine, expire_on_commit=False)
            async with factory() as session:
                result_id = await run_recommendation_pipeline(
                    UUID(org_id),
                    session,
                    existing_run_id=UUID(run_id) if run_id else None,
                )
                return str(result_id)
        finally:
            await _engine.dispose()

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("recommendation_pipeline", metadata={"org_id": org_id}):
                result_id = asyncio.run(_run())
        return result_id
    finally:
        flush_langfuse()


@celery_app.task(name="recommendations.evaluate_agent_financials")
def evaluate_agent_financials_task(org_id: str, run_id: str) -> str:
    """Async financial evaluation for agent opportunities (Phase 4).

    Reads financial_signals from each pending recommendation, assembles
    assumptions, runs compute_projections, writes back results.
    """
    import asyncio
    import logging

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span
    from app.services.recommendations.recompute import recompute_recommendation

    logger = logging.getLogger(__name__)

    async def _run() -> str:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.recommendation import Recommendation

        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(_engine, expire_on_commit=False)
            async with factory() as session:
                q = await session.execute(
                    select(Recommendation).where(
                        Recommendation.org_id == UUID(org_id),
                        Recommendation.recommendation_run_id == UUID(run_id),
                        Recommendation.financial_evaluation_status == "pending",
                    )
                )
                recs = list(q.scalars().all())
                evaluated = 0
                for rec in recs:
                    try:
                        result = recompute_recommendation(rec)
                        if result["financial_status"] == "completed":
                            evaluated += 1
                    except Exception:
                        logger.exception("financial_eval_failed rec=%s", rec.id)
                        rec.financial_evaluation_status = "failed"
                    if evaluated % 5 == 0:
                        await session.commit()
                await session.commit()
                return f"evaluated={evaluated} total={len(recs)}"
        finally:
            await _engine.dispose()

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("financial_evaluation", metadata={"org_id": org_id, "run_id": run_id}):
                result = asyncio.run(_run())
        return result
    finally:
        flush_langfuse()
