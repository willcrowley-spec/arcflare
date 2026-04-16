"""Sync progress tracking via Redis hashes."""
import logging
from datetime import UTC, datetime
from typing import Any

import redis

logger = logging.getLogger(__name__)

PHASES = [
    "objects",
    "fields",
    "flows",
    "triggers",
    "validation_rules",
    "apex_classes",
    "permissions",
    "ui_components",
    "reports",
    "installed_packages",
    "licensing",
    "user_velocity",
    "vectorization",
]

_KEY_PREFIX = "sync_progress"


def _key(connection_id: str) -> str:
    return f"{_KEY_PREFIX}:{connection_id}"


def get_redis_client() -> redis.Redis:
    from app.core.config import get_settings
    return redis.from_url(get_settings().REDIS_URL, decode_responses=True)


def init_progress(connection_id: str, r: redis.Redis | None = None) -> None:
    r = r or get_redis_client()
    k = _key(connection_id)
    mapping: dict[str, str] = {
        "status": "running",
        "started_at": datetime.now(tz=UTC).isoformat(),
        "completed_at": "",
        "error": "",
    }
    for phase in PHASES:
        mapping[phase] = "waiting:0"
    r.hset(k, mapping=mapping)
    r.expire(k, 3600)


def update_phase(
    connection_id: str,
    phase: str,
    status: str,
    count: int = 0,
    r: redis.Redis | None = None,
) -> None:
    r = r or get_redis_client()
    r.hset(_key(connection_id), phase, f"{status}:{count}")


def complete_progress(
    connection_id: str,
    error: str | None = None,
    r: redis.Redis | None = None,
) -> None:
    r = r or get_redis_client()
    k = _key(connection_id)
    r.hset(k, mapping={
        "status": "failed" if error else "completed",
        "completed_at": datetime.now(tz=UTC).isoformat(),
        "error": error or "",
    })
    r.expire(k, 300)


def get_progress(connection_id: str, r: redis.Redis | None = None) -> dict[str, Any]:
    r = r or get_redis_client()
    raw = r.hgetall(_key(connection_id))
    if not raw:
        return {"status": "idle"}
    phases: dict[str, dict[str, Any]] = {}
    for phase in PHASES:
        val = raw.get(phase, "waiting:0")
        parts = val.split(":", 1)
        phases[phase] = {
            "status": parts[0],
            "count": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
        }
    return {
        "status": raw.get("status", "idle"),
        "started_at": raw.get("started_at") or None,
        "completed_at": raw.get("completed_at") or None,
        "error": raw.get("error") or None,
        "phases": phases,
    }
