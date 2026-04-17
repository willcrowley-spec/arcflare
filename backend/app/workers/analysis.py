from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="recommendations.generate_recommendations")
def generate_recommendations_task(org_id: str) -> str:
    """Run analyzer + scorer and persist Recommendation rows."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import engine
    from app.models.recommendation import Recommendation
    from app.services.recommendations.analyzer import analyze_org
    from app.services.recommendations.scorer import score_recommendation

    from app.core.observability import flush_langfuse

    async def _run() -> int:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            oid = UUID(org_id)
            patterns = await analyze_org(oid, session)
            candidates = score_recommendation(patterns)
            for rec in candidates:
                session.add(rec)
            await session.commit()
            return len(candidates)

    try:
        asyncio.run(_run())
        return org_id
    finally:
        flush_langfuse()
