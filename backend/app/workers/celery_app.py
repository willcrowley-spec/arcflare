from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "arcflare",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.include = [
    "app.workers.metadata_sync",
    "app.workers.telemetry_poll",
    "app.workers.vectorization",
    "app.workers.analysis",
    "app.workers.process_discovery",
    "app.workers.org_research",
    "app.workers.agent_generation",
    "app.services.prompts.optimize",
]
