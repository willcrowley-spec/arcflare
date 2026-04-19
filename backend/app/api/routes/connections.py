import asyncio
import base64
import json as json_mod
from datetime import UTC, datetime
from typing import AsyncGenerator
from uuid import UUID

import redis
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import delete, select as sa_select

from app.api.deps import CurrentOrg, CurrentUserDep, DbSession
from app.core.security import encrypt_tokens
from app.models.connection import PlatformConnection
from app.models.sync_event import SyncEvent
from app.services.salesforce import oauth as sf_oauth
from app.schemas.connection import ConnectionList, ConnectionResponse
from app.workers.metadata_sync import sync_metadata_task

router = APIRouter()


@router.post("/salesforce/initiate", status_code=status.HTTP_200_OK)
async def salesforce_initiate(
    org: CurrentOrg,
    user: CurrentUserDep,
) -> dict[str, str]:
    """Start Salesforce OAuth; returns authorize URL and opaque state."""
    del user  # reserved for audit logging
    payload = {"clerk_org_id": org.clerk_org_id, "ts": datetime.now(tz=UTC).isoformat()}
    oauth_state = base64.urlsafe_b64encode(json_mod.dumps(payload).encode("utf-8")).decode("utf-8")
    url, _ = sf_oauth.generate_auth_url(oauth_state=oauth_state)
    return {"authorization_url": url, "state": oauth_state}


@router.get("/salesforce/callback")
async def salesforce_callback(
    db: DbSession,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    """OAuth redirect target: exchanges code, stores encrypted tokens, redirects to frontend."""
    from app.core.config import get_settings

    settings = get_settings()
    try:
        padded = state + "=" * (-len(state) % 4)
        raw = json_mod.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
        clerk_org_id = raw["clerk_org_id"]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid state") from exc

    from app.models.organization import Organization

    org_result = await db.execute(
        sa_select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    tokens = await sf_oauth.handle_callback(code)
    enc = encrypt_tokens(json_mod.dumps(tokens), settings)

    # Extract Salesforce org ID from the token "id" URL
    # Format: https://login.salesforce.com/id/00Dxx.../005xx...
    sf_org_id = ""
    id_url = tokens.get("id", "")
    if "/id/" in id_url:
        parts = id_url.split("/id/")[1].split("/")
        sf_org_id = parts[0] if parts else ""

    # Upsert: find existing connection for this SF org, or create new
    existing = await db.execute(
        sa_select(PlatformConnection).where(
            PlatformConnection.org_id == org.id,
            PlatformConnection.platform_type == "salesforce",
            PlatformConnection.platform_org_id == sf_org_id,
        )
    )
    conn = existing.scalar_one_or_none()

    if conn:
        conn.oauth_tokens_encrypted = enc
        conn.instance_url = tokens.get("instance_url")
        conn.status = "connected"
    else:
        conn = PlatformConnection(
            org_id=org.id,
            platform_type="salesforce",
            platform_org_id=sf_org_id,
            instance_url=tokens.get("instance_url"),
            oauth_tokens_encrypted=enc,
            status="connected",
            entity_count=0,
            last_sync_at=None,
            sync_config_json={},
        )
        db.add(conn)

    await db.commit()
    await db.refresh(conn)
    sync_metadata_task.delay(str(conn.id))
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/#/analysis?connected=salesforce",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/{connection_id}/reauth", status_code=status.HTTP_200_OK)
async def reauth_connection(
    connection_id: UUID,
    org: CurrentOrg,
    user: CurrentUserDep,
    db: DbSession,
) -> dict[str, str]:
    """Start OAuth re-authentication for an existing connection."""
    del user
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    if conn.platform_type != "salesforce":
        raise HTTPException(status_code=400, detail=f"Re-auth not yet supported for {conn.platform_type}")

    payload = {
        "clerk_org_id": org.clerk_org_id,
        "ts": datetime.now(tz=UTC).isoformat(),
        "connection_id": str(connection_id),
    }
    oauth_state = base64.urlsafe_b64encode(json_mod.dumps(payload).encode("utf-8")).decode("utf-8")
    url, _ = sf_oauth.generate_auth_url(oauth_state=oauth_state)
    return {"authorization_url": url, "state": oauth_state}


@router.get("/", response_model=ConnectionList)
async def list_connections(
    db: DbSession,
    org: CurrentOrg,
) -> ConnectionList:
    """List Salesforce (and other) connections for the org."""
    q = await db.execute(
        sa_select(PlatformConnection).where(PlatformConnection.org_id == org.id)
    )
    rows = q.scalars().all()
    items = [ConnectionResponse.model_validate(r) for r in rows]
    return ConnectionList(connections=items, total=len(items))


@router.post("/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_connection(
    connection_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str]:
    """Enqueue metadata sync for a connection."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn.status = "syncing"
    await db.commit()
    sync_metadata_task.delay(str(conn.id))
    return {"status": "queued", "connection_id": str(conn.id)}


@router.get("/{connection_id}/sync-stream")
async def sync_event_stream(
    connection_id: UUID,
    org: CurrentOrg,
    db: DbSession,
) -> StreamingResponse:
    """SSE stream of sync events — backfills latest run then streams live."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        from app.services.sync_progress import get_redis_client

        r = get_redis_client()
        channel = f"sync_events:{connection_id}"
        loop = asyncio.get_running_loop()

        latest_run_q = await db.execute(
            sa_select(SyncEvent)
            .where(SyncEvent.connection_id == connection_id)
            .order_by(SyncEvent.created_at.desc())
            .limit(1)
        )
        latest_event = latest_run_q.scalar_one_or_none()
        latest_run_id = latest_event.run_id if latest_event else None
        backfill_events: list[SyncEvent] = []
        last_seq = 0

        if latest_run_id:
            backfill_q = await db.execute(
                sa_select(SyncEvent)
                .where(
                    SyncEvent.connection_id == connection_id,
                    SyncEvent.run_id == latest_run_id,
                )
                .order_by(SyncEvent.sequence)
            )
            backfill_events = list(backfill_q.scalars().all())
            last_seq = max((e.sequence for e in backfill_events), default=0)
            backfill_data = [
                {
                    "run_id": str(e.run_id),
                    "sequence": e.sequence,
                    "event_type": e.event_type,
                    "phase": e.phase,
                    "message": e.message,
                    "detail": e.detail_json,
                    "severity": e.severity,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in backfill_events
            ]
            yield f"event: backfill\ndata: {json_mod.dumps(backfill_data)}\n\n"

            is_done = any(
                e.event_type == "run_complete"
                or (e.event_type == "error" and e.severity == "error")
                for e in backfill_events
            )
            if is_done:
                await db.refresh(conn)
                if conn.status != "syncing":
                    yield "event: done\ndata: {}\n\n"
                    return

        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        try:
            if latest_run_id:
                gap_q = await db.execute(
                    sa_select(SyncEvent)
                    .where(
                        SyncEvent.connection_id == connection_id,
                        SyncEvent.run_id == latest_run_id,
                        SyncEvent.sequence > last_seq,
                    )
                    .order_by(SyncEvent.sequence)
                )
                for row in gap_q.scalars().all():
                    payload = {
                        "run_id": str(row.run_id),
                        "connection_id": str(connection_id),
                        "sequence": row.sequence,
                        "event_type": row.event_type,
                        "phase": row.phase,
                        "message": row.message,
                        "detail": row.detail_json,
                        "severity": row.severity,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                    yield f"event: sync_event\ndata: {json_mod.dumps(payload)}\n\n"

            last_keepalive = loop.time()

            def _is_terminal(parsed: dict) -> bool:
                et = parsed.get("event_type")
                if et == "run_complete":
                    return True
                return et == "error" and parsed.get("severity") == "error"

            while True:
                msg = await asyncio.to_thread(
                    pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield f"event: sync_event\ndata: {data}\n\n"
                    parsed = json_mod.loads(data)
                    if _is_terminal(parsed):
                        yield "event: done\ndata: {}\n\n"
                        return

                now = loop.time()
                if now - last_keepalive > 15:
                    yield ": keepalive\n\n"
                    last_keepalive = now

                await asyncio.sleep(0.25)
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{connection_id}/sync-events")
async def get_sync_events(
    connection_id: UUID,
    org: CurrentOrg,
    db: DbSession,
    run_id: UUID | None = Query(default=None),
) -> list[dict]:
    """Return events for a specific run, or the latest run. Useful for debugging via curl."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    if run_id is None:
        latest_q = await db.execute(
            sa_select(SyncEvent.run_id)
            .where(SyncEvent.connection_id == connection_id)
            .order_by(SyncEvent.created_at.desc())
            .limit(1)
        )
        row = latest_q.first()
        if not row:
            return []
        run_id = row[0]

    q = await db.execute(
        sa_select(SyncEvent)
        .where(
            SyncEvent.connection_id == connection_id,
            SyncEvent.run_id == run_id,
        )
        .order_by(SyncEvent.sequence)
    )
    return [
        {
            "id": str(e.id),
            "run_id": str(e.run_id),
            "sequence": e.sequence,
            "event_type": e.event_type,
            "phase": e.phase,
            "message": e.message,
            "detail": e.detail_json,
            "severity": e.severity,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in q.scalars().all()
    ]


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> None:
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.execute(delete(PlatformConnection).where(PlatformConnection.id == connection_id))
    await db.commit()
