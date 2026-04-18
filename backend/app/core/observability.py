"""Langfuse observability — v3 SDK (OpenTelemetry-native).

Provides a shared Langfuse client and context-manager helpers that safely
wrap LLM calls and pipeline spans.  All helpers degrade to no-ops when
Langfuse is not configured.
"""
import logging
import sys
from contextlib import contextmanager
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


def shutdown_langfuse():
    """Graceful shutdown — flush and release the client. Call from FastAPI lifespan."""
    global _langfuse_client
    lf = _langfuse_client
    if lf is not None:
        try:
            lf.flush()
        except Exception as e:
            logger.warning("langfuse_shutdown_flush_failed error=%s", e)
    _langfuse_client = None
    logger.info("langfuse_shutdown_complete")


# ---------------------------------------------------------------------------
# v3 context-manager helpers
#
# Design: Langfuse setup errors are swallowed (yield None so caller runs
# normally).  Exceptions from *user code* inside the block always propagate
# — a @contextmanager can only yield once, so we must never yield in an
# except handler.
# ---------------------------------------------------------------------------

def _open_observation(lf, **kwargs):
    """Try to open a Langfuse observation, return (ctx_manager, obs) or (None, None)."""
    try:
        mgr = lf.start_as_current_observation(**kwargs)
        obs = mgr.__enter__()
        return mgr, obs
    except Exception as e:
        logger.warning("langfuse_observation_open_failed name=%s error=%s", kwargs.get("name"), e)
        return None, None


def _close_observation(mgr):
    """Close a Langfuse observation context, passing current exception info."""
    if mgr is None:
        return
    try:
        mgr.__exit__(*sys.exc_info())
    except Exception:
        pass


@contextmanager
def langfuse_context(
    user_id: str | None = None,
    org_id: str | None = None,
    session_id: str | None = None,
) -> Generator[None, None, None]:
    """Propagate user/org/session to all nested Langfuse observations.

    Must wrap the outermost scope (API route handler, Celery task) so that
    every ``langfuse_span`` and ``langfuse_generation`` inside automatically
    inherits ``user_id``, ``session_id``, tags, and metadata.
    """
    lf = get_langfuse()
    if lf is None:
        yield
        return

    tags: list[str] = []
    if org_id:
        tags.append(f"org:{org_id}")
    meta: dict[str, str] = {}
    if org_id:
        meta["org_id"] = org_id
    if user_id:
        meta["user_id"] = user_id

    try:
        from langfuse import propagate_attributes

        with propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            tags=tags,
            metadata=meta,
        ):
            yield
    except Exception as e:
        logger.warning("langfuse_context_failed error=%s", e)
        yield


@contextmanager
def langfuse_span(
    name: str,
    metadata: dict[str, Any] | None = None,
    input: Any | None = None,
    session_id: str | None = None,
) -> Generator[Any, None, None]:
    """Open a Langfuse span (pipeline-level observation).

    Yields the observation object (or ``None`` when Langfuse is disabled).
    Child observations created inside the ``with`` block are auto-nested
    via OTEL context propagation.

    When ``session_id`` is set, attempts to attach it via Langfuse
    ``propagate_attributes`` so nested generations share the same session.
    """
    lf = get_langfuse()
    if lf is None:
        yield None
        return

    prop_mgr = None
    if session_id:
        try:
            from langfuse import propagate_attributes

            prop_mgr = propagate_attributes(session_id=session_id)
            prop_mgr.__enter__()
        except Exception as e:
            logger.debug("langfuse_propagate_session_failed error=%s", e)
            prop_mgr = None

    meta = dict(metadata or {})
    if session_id and prop_mgr is None:
        meta.setdefault("session_id", session_id)

    mgr, obs = _open_observation(lf, as_type="span", name=name, metadata=meta, input=input)
    try:
        yield obs
    finally:
        _close_observation(mgr)
        if prop_mgr is not None:
            try:
                prop_mgr.__exit__(None, None, None)
            except Exception:
                pass


@contextmanager
def langfuse_generation(
    name: str,
    model: str | None = None,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Open a Langfuse generation observation.

    Yields the observation object (or ``None``).  Caller should call
    ``obs.update(output=..., usage_details=..., cost_details=...)`` before
    exiting.
    """
    lf = get_langfuse()
    if lf is None:
        yield None
        return

    mgr, obs = _open_observation(
        lf, as_type="generation", name=name, model=model, input=input, metadata=metadata,
    )
    try:
        yield obs
    finally:
        _close_observation(mgr)


def langfuse_score(name: str, value: float, comment: str | None = None) -> None:
    """Post a numeric score to the current Langfuse trace.

    Must be called inside an active ``langfuse_span`` or ``langfuse_generation``
    context so the score attaches to the correct trace.
    """
    lf = get_langfuse()
    if lf is None:
        return
    try:
        lf.score(name=name, value=value, comment=comment)
    except Exception as e:
        logger.debug("langfuse_score_failed name=%s error=%s", name, e)
