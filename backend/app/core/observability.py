"""Langfuse observability client for tracing LLM calls, embeddings, and pipelines."""
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_langfuse_client = None


def get_langfuse():
    """Return a shared Langfuse client instance, or None if not configured."""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    settings = get_settings()
    sk = (settings.LANGFUSE_SECRET_KEY or "").strip()
    pk = (settings.LANGFUSE_PUBLIC_KEY or "").strip()
    if not sk or not pk:
        logger.debug("langfuse_disabled reason=missing_keys")
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            secret_key=sk,
            public_key=pk,
            host=settings.LANGFUSE_BASE_URL or "https://cloud.langfuse.com",
            enabled=True,
        )
        logger.info("langfuse_initialized host=%s", settings.LANGFUSE_BASE_URL)
        return _langfuse_client
    except Exception as e:
        logger.warning("langfuse_init_failed error=%s", e)
        return None


def flush_langfuse():
    """Flush pending Langfuse events. Call at end of Celery tasks."""
    lf = get_langfuse()
    if lf is not None:
        try:
            lf.flush()
        except Exception as e:
            logger.warning("langfuse_flush_failed error=%s", e)
