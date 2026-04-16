import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from app.api.deps import CurrentOrg, CurrentUserDep, DbSession
from app.core.security import encrypt_tokens
from app.models.connection import PlatformConnection
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
    oauth_state = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
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
        raw = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
        clerk_org_id = raw["clerk_org_id"]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid state") from exc

    from app.models.organization import Organization

    org_result = await db.execute(
        select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    tokens = await sf_oauth.handle_callback(code)
    enc = encrypt_tokens(json.dumps(tokens), settings)

    conn = PlatformConnection(
        org_id=org.id,
        platform_type="salesforce",
        instance_url=tokens.get("instance_url"),
        oauth_tokens_encrypted=enc,
        status="connected",
        entity_count=0,
        last_sync_at=None,
        sync_config_json={},
    )
    db.add(conn)
    await db.commit()
    sync_metadata_task.delay(str(conn.id))
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/#/analysis?connected=salesforce",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/", response_model=ConnectionList)
async def list_connections(
    db: DbSession,
    org: CurrentOrg,
) -> ConnectionList:
    """List Salesforce (and other) connections for the org."""
    q = await db.execute(
        select(PlatformConnection).where(PlatformConnection.org_id == org.id)
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
    sync_metadata_task.delay(str(conn.id))
    return {"status": "queued", "connection_id": str(conn.id)}


@router.get("/{connection_id}/sync-status")
async def get_sync_status(
    connection_id: UUID,
    org: CurrentOrg,
    db: DbSession,
) -> dict:
    """Return live sync progress from Redis."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    from app.services.sync_progress import get_progress
    return get_progress(str(connection_id))


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
