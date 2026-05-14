from __future__ import annotations

from app.workers.celery_app import celery_app


@celery_app.task(name="agent_generation.validate_source_bundle")
def validate_agent_source_bundle_task(validation_run_id: str) -> str:
    """Feature-flagged scratch validation placeholder.

    The API stores source artifacts now. The worker is intentionally conservative
    until server-side Salesforce CLI auth and scratch-org cleanup are configured
    in the deployment environment.
    """
    import asyncio
    from datetime import UTC, datetime
    from uuid import UUID

    async def _run() -> str:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.agent_design import ScratchValidationRun

        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(_engine, expire_on_commit=False)
            async with factory() as session:
                validation = await session.get(ScratchValidationRun, UUID(validation_run_id))
                if validation is None:
                    return "not_found"
                validation.status = "blocked"
                validation.error = (
                    "Scratch org validation is queued, but the server-side CLI execution "
                    "adapter is not enabled in this build. Download the source bundle or "
                    "enable the validation adapter after integration-user auth is configured."
                )
                validation.logs_json = [
                    {
                        "level": "warning",
                        "message": validation.error,
                        "devhub_alias": settings.SALESFORCE_DEV_HUB_ALIAS,
                    }
                ]
                validation.result_json = {
                    "feature_flag_enabled": settings.AGENTFORCE_SCRATCH_VALIDATION_ENABLED,
                    "adapter": "pending_server_cli_auth",
                }
                validation.completed_at = datetime.now(tz=UTC)
                await session.commit()
                return "blocked"
        finally:
            await _engine.dispose()

    return asyncio.run(_run())
