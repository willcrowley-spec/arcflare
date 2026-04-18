"""Langfuse observability — v3 SDK (OpenTelemetry-native).

Provides a shared Langfuse client and context-manager helpers that safely
wrap LLM calls and pipeline spans.  All helpers degrade to no-ops when
Langfuse is not configured.
"""
import logging
from contextlib import contextmanager, nullcontext
from typing import Any, Generator

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


# ---------------------------------------------------------------------------
# v3 context-manager helpers
# ---------------------------------------------------------------------------

@contextmanager
def langfuse_span(
    name: str,
    metadata: dict[str, Any] | None = None,
    input: Any | None = None,
) -> Generator[Any, None, None]:
    """Open a Langfuse span (pipeline-level observation).

    Yields the observation object (or ``None`` when Langfuse is disabled).
    Child observations created inside the ``with`` block are auto-nested
    via OTEL context propagation.
    """
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    try:
        with lf.start_as_current_observation(
            as_type="span",
            name=name,
            metadata=metadata,
            input=input,
        ) as obs:
            yield obs
    except Exception as e:
        logger.warning("langfuse_span_failed name=%s error=%s", name, e)
        yield None


@contextmanager
def langfuse_generation(
    name: str,
    model: str | None = None,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Open a Langfuse generation observation.

    Yields the observation object (or ``None``).  Caller should call
    ``obs.update(output=..., usage=...)`` before exiting.
    """
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    try:
        with lf.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input,
            metadata=metadata,
        ) as obs:
            yield obs
    except Exception as e:
        logger.warning("langfuse_generation_failed name=%s error=%s", name, e)
        yield None
