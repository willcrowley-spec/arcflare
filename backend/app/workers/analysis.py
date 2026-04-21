from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="recommendations.generate_recommendations")
def generate_recommendations_task(org_id: str) -> str:
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span
    from app.services.recommendations.pipeline import run_recommendation_pipeline

    async def _run() -> str:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            run_id = await run_recommendation_pipeline(UUID(org_id), session)
            return str(run_id)

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("recommendation_pipeline", metadata={"org_id": org_id}):
                run_id = asyncio.run(_run())
        return run_id
    finally:
        flush_langfuse()
