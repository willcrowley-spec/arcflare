"""Structured sync event logging — Postgres persistence + Redis pub/sub."""
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_event import SyncEvent
from app.services.sync_progress import get_redis_client

logger = logging.getLogger(__name__)


class SyncEventEmitter:
    """Emits structured sync events to Postgres + Redis pub/sub."""

    def __init__(
        self,
        connection_id: UUID,
        org_id: UUID,
        run_id: UUID,
        db: AsyncSession,
    ) -> None:
        self.connection_id = connection_id
        self.org_id = org_id
        self.run_id = run_id
        self.db = db
        self._sequence = 0
        self._redis = get_redis_client()
        self._channel = f"sync_events:{connection_id}"

    async def emit(
        self,
        event_type: str,
        message: str,
        *,
        phase: str | None = None,
        detail: dict | None = None,
        severity: str = "info",
    ) -> None:
        self._sequence += 1
        now = datetime.now(tz=UTC)
        event = SyncEvent(
            connection_id=self.connection_id,
            org_id=self.org_id,
            run_id=self.run_id,
            sequence=self._sequence,
            event_type=event_type,
            phase=phase,
            message=message,
            detail_json=detail or {},
            severity=severity,
            created_at=now,
        )
        self.db.add(event)
        await self.db.flush()

        payload = {
            "run_id": str(self.run_id),
            "connection_id": str(self.connection_id),
            "sequence": self._sequence,
            "event_type": event_type,
            "phase": phase,
            "message": message,
            "detail": detail or {},
            "severity": severity,
            "created_at": now.isoformat(),
        }
        try:
            self._redis.publish(self._channel, json.dumps(payload))
        except Exception:
            logger.warning("redis_publish_failed channel=%s", self._channel, exc_info=True)

    async def purge_old_runs(self) -> None:
        """Delete all but the 2 most recent previous runs for this connection."""
        await self.db.execute(
            text("""
                DELETE FROM sync_events
                WHERE connection_id = :cid
                AND run_id NOT IN (
                    SELECT run_id FROM (
                        SELECT run_id, MAX(created_at) AS latest
                        FROM sync_events
                        WHERE connection_id = :cid
                        GROUP BY run_id
                        ORDER BY latest DESC
                        LIMIT 2
                    ) AS recent
                )
            """),
            {"cid": self.connection_id},
        )
        await self.db.flush()
