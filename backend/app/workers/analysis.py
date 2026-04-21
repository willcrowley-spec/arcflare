from uuid import UUID

from app.workers.celery_app import celery_app


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
