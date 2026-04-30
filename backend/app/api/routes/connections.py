import asyncio
import base64
import hashlib
import hmac
import json as json_mod
import logging
import time
from typing import AsyncGenerator
from urllib.parse import urlencode
from uuid import UUID

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
logger = logging.getLogger(__name__)

_OAUTH_STATE_TTL_SECONDS = 10 * 60


def _frontend_redirect_url(base_url: str, **params: str) -> str:
    query = urlencode({k: v for k, v in params.items() if v})
    return f"{base_url.rstrip('/')}/#/analysis{f'?{query}' if query else ''}"


def _state_secret(settings: object) -> bytes:
    for name in ("ENCRYPTION_KEY", "CLERK_SECRET_KEY", "SALESFORCE_CLIENT_SECRET"):
        value = str(getattr(settings, name, "") or "").strip()
        if value:
            return value.encode("utf-8")
    raise RuntimeError("No application secret available for OAuth state signing")


def _b64_json(data: dict) -> str:
    raw = json_mod.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64_json(data: str) -> dict:
    padded = data + "=" * (-len(data) % 4)
    return json_mod.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))


def _build_oauth_state(payload: dict, settings: object) -> str:
    body = dict(payload)
    body["ts"] = int(time.time())
    encoded = _b64_json(body)
    sig = hmac.new(_state_secret(settings), encoded.encode("utf-8"), hashlib.sha256).digest()
    return f"{encoded}.{_b64_bytes(sig)}"


def _parse_oauth_state(state: str, settings: object) -> dict:
    try:
        encoded, supplied_sig = state.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid OAuth state format") from exc

    expected = hmac.new(_state_secret(settings), encoded.encode("utf-8"), hashlib.sha256).digest()
    padded_sig = supplied_sig + "=" * (-len(supplied_sig) % 4)
    try:
        supplied = base64.urlsafe_b64decode(padded_sig.encode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid OAuth state signature") from exc
    if not hmac.compare_digest(expected, supplied):
        raise ValueError("Invalid OAuth state signature")

    payload = _unb64_json(encoded)
    ts = int(payload.get("ts") or 0)
    if ts <= 0 or int(time.time()) - ts > _OAUTH_STATE_TTL_SECONDS:
        raise ValueError("Expired OAuth state")
    return payload


def _extract_salesforce_org_id(tokens: dict) -> str:
    id_url = str(tokens.get("id") or "")
    if "/id/" not in id_url:
        return ""
    parts = id_url.split("/id/", 1)[1].split("/")
    return parts[0] if parts else ""


def _salesforce_authorization_error(error: str | None) -> str:
    if error == "OAUTH_AUTHORIZATION_BLOCKED":
        return "salesforce_authorization_blocked"
    if error == "access_denied":
        return "salesforce_access_denied"
    if error in {"invalid_request", "invalid_client", "invalid_scope", "server_error"}:
        return f"salesforce_{error}"
    return "salesforce_authorization_failed"


@router.post("/salesforce/initiate", status_code=status.HTTP_200_OK)
async def salesforce_initiate(
    org: CurrentOrg,
    user: CurrentUserDep,
    db: DbSession,
) -> dict[str, str]:
    """Start Salesforce OAuth; returns authorize URL and opaque state."""
    existing = await db.execute(
        sa_select(PlatformConnection).where(
            PlatformConnection.org_id == org.id,
            PlatformConnection.platform_type == "salesforce",
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Salesforce is already connected for this organization",
        )

    from app.core.config import get_settings

    settings = get_settings()
    payload = {
        "action": "connect",
        "clerk_org_id": org.clerk_org_id,
        "clerk_user_id": user.clerk_user_id,
    }
    oauth_state = _build_oauth_state(payload, settings)
    url, _ = sf_oauth.generate_auth_url(oauth_state=oauth_state)
    return {"authorization_url": url, "state": oauth_state}


@router.get("/salesforce/callback")
async def salesforce_callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    salesforce_error: str | None = Query(default=None, alias="error"),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """OAuth redirect target: exchanges code, stores encrypted tokens, redirects to frontend."""
    from app.core.config import get_settings

    settings = get_settings()
    if salesforce_error:
        logger.warning(
            "Salesforce OAuth authorization failed: error=%s description=%s state_present=%s",
            salesforce_error,
            error_description,
            bool(state),
        )
        return RedirectResponse(
            url=_frontend_redirect_url(
                settings.FRONTEND_URL,
                connection_error=_salesforce_authorization_error(salesforce_error),
            ),
            status_code=status.HTTP_302_FOUND,
        )

    if not code:
        logger.warning("Salesforce OAuth callback missing authorization code; state_present=%s", bool(state))
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="missing_authorization_code"),
            status_code=status.HTTP_302_FOUND,
        )

    if not state:
        logger.warning("Salesforce OAuth callback missing state")
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="invalid_state"),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        raw = _parse_oauth_state(state, settings)
        clerk_org_id = raw["clerk_org_id"]
        action = raw.get("action")
    except Exception:
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="invalid_state"),
            status_code=status.HTTP_302_FOUND,
        )

    from app.models.organization import Organization

    org_result = await db.execute(
        sa_select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="org_not_found"),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        tokens = await sf_oauth.handle_callback(code)
    except Exception:
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="token_exchange_failed"),
            status_code=status.HTTP_302_FOUND,
        )

    sf_org_id = _extract_salesforce_org_id(tokens)
    if not sf_org_id:
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="missing_salesforce_org"),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        enc = encrypt_tokens(json_mod.dumps(tokens), settings)
    except Exception:
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="token_storage_failed"),
            status_code=status.HTTP_302_FOUND,
        )

    if action == "reauth":
        raw_connection_id = raw.get("connection_id")
        try:
            connection_id = UUID(str(raw_connection_id))
        except (TypeError, ValueError):
            return RedirectResponse(
                url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="invalid_connection"),
                status_code=status.HTTP_302_FOUND,
            )
        conn = await db.get(PlatformConnection, connection_id)
        if conn is None or conn.org_id != org.id or conn.platform_type != "salesforce":
            return RedirectResponse(
                url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="connection_not_found"),
                status_code=status.HTTP_302_FOUND,
            )
        if conn.platform_org_id and conn.platform_org_id != sf_org_id:
            return RedirectResponse(
                url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="salesforce_org_mismatch"),
                status_code=status.HTTP_302_FOUND,
            )
        conn.platform_org_id = sf_org_id
        conn.oauth_tokens_encrypted = enc
        conn.instance_url = tokens.get("instance_url")
        conn.status = "connected"
    elif action == "connect":
        existing = await db.execute(
            sa_select(PlatformConnection).where(
                PlatformConnection.org_id == org.id,
                PlatformConnection.platform_type == "salesforce",
            )
        )
        if existing.scalar_one_or_none() is not None:
            return RedirectResponse(
                url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="salesforce_already_connected"),
                status_code=status.HTTP_302_FOUND,
            )
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
    else:
        return RedirectResponse(
            url=_frontend_redirect_url(settings.FRONTEND_URL, connection_error="invalid_action"),
            status_code=status.HTTP_302_FOUND,
        )

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
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    if conn.platform_type != "salesforce":
        raise HTTPException(status_code=400, detail=f"Re-auth not yet supported for {conn.platform_type}")

    from app.core.config import get_settings

    settings = get_settings()
    payload = {
        "action": "reauth",
        "clerk_org_id": org.clerk_org_id,
        "clerk_user_id": user.clerk_user_id,
        "connection_id": str(connection_id),
    }
    oauth_state = _build_oauth_state(payload, settings)
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
    if conn.status == "syncing":
        raise HTTPException(status_code=409, detail="Sync already in progress")
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
        from app.core.database import async_session_factory
        from app.services.sync_progress import get_redis_client

        r = get_redis_client()
        channel = f"sync_events:{connection_id}"
        loop = asyncio.get_running_loop()

        async with async_session_factory() as session:
            latest_run_q = await session.execute(
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
                backfill_q = await session.execute(
                    sa_select(SyncEvent)
                    .where(
                        SyncEvent.connection_id == connection_id,
                        SyncEvent.run_id == latest_run_id,
                    )
                    .order_by(SyncEvent.sequence)
                )
                backfill_events = list(backfill_q.scalars().all())
                last_seq = max((e.sequence for e in backfill_events), default=0)

                is_done = any(
                    e.event_type == "run_complete"
                    or (e.event_type == "error" and e.severity == "error")
                    for e in backfill_events
                )

                fresh = await session.execute(
                    sa_select(PlatformConnection.status)
                    .where(PlatformConnection.id == connection_id)
                )
                conn_status = fresh.scalar_one_or_none()

                actively_syncing = conn_status == "syncing"

                if is_done and actively_syncing:
                    # Previous run complete but a new sync just started — skip
                    # stale backfill and fall through to Redis subscribe.
                    pass
                else:
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

                    if is_done or not actively_syncing:
                        # Run finished normally, OR the run is orphaned (task
                        # crashed without emitting a terminal event and the
                        # connection is no longer syncing). Either way, close.
                        yield "event: done\ndata: {}\n\n"
                        return

            # Gap replay — catch events emitted between backfill query and subscribe
            pubsub = r.pubsub()
            pubsub.subscribe(channel)
            try:
                if latest_run_id:
                    gap_q = await session.execute(
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
            finally:
                # Session only needed for DB queries; close before entering
                # the long-lived Redis poll loop so the connection returns to pool.
                await session.close()

        last_keepalive = loop.time()

        def _is_terminal(parsed: dict) -> bool:
            et = parsed.get("event_type")
            if et == "run_complete":
                return True
            return et == "error" and parsed.get("severity") == "error"

        try:
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
