"""Salesforce OAuth 2.0 web server flow helpers."""

import json
import secrets
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import decrypt_tokens, encrypt_tokens
from app.models.connection import PlatformConnection


def generate_auth_url(
    oauth_state: str | None = None,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """
    Build Salesforce authorization URL and return (url, state).

    Uses SALESFORCE_CLIENT_ID, SALESFORCE_REDIRECT_URI from settings.
    """
    settings = settings or get_settings()
    if not settings.SALESFORCE_CLIENT_ID or not settings.SALESFORCE_REDIRECT_URI:
        raise RuntimeError("Salesforce OAuth is not configured")

    state = oauth_state or secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": settings.SALESFORCE_CLIENT_ID,
        "redirect_uri": settings.SALESFORCE_REDIRECT_URI,
        "scope": "api refresh_token",
        "state": state,
    }
    base = "https://login.salesforce.com/services/oauth2/authorize"
    return f"{base}?{urlencode(params)}", state


async def handle_callback(code: str, settings: Settings | None = None) -> dict:
    """
    Exchange authorization code for access and refresh tokens.

    Returns token payload from Salesforce (access_token, refresh_token, instance_url, ...).
    """
    settings = settings or get_settings()
    if not settings.SALESFORCE_CLIENT_SECRET:
        raise RuntimeError("SALESFORCE_CLIENT_SECRET is not configured")

    token_url = "https://login.salesforce.com/services/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.SALESFORCE_CLIENT_ID,
        "client_secret": settings.SALESFORCE_CLIENT_SECRET,
        "redirect_uri": settings.SALESFORCE_REDIRECT_URI,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        return resp.json()


async def _exchange_refresh_token(refresh_token: str, settings: Settings | None = None) -> dict:
    """Refresh Salesforce access token using refresh_token string."""
    settings = settings or get_settings()
    token_url = "https://login.salesforce.com/services/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": settings.SALESFORCE_CLIENT_ID,
        "client_secret": settings.SALESFORCE_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(
    connection_id: UUID,
    db: AsyncSession,
    settings: Settings | None = None,
) -> dict:
    """
    Load encrypted OAuth payload for a PlatformConnection and refresh tokens.
    Persists updated access token JSON back to the row.
    """
    settings = settings or get_settings()
    result = await db.execute(select(PlatformConnection).where(PlatformConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if conn is None or not conn.oauth_tokens_encrypted:
        raise ValueError("Connection or tokens not found")
    payload = json.loads(decrypt_tokens(conn.oauth_tokens_encrypted, settings))
    refresh = payload.get("refresh_token")
    if not refresh:
        raise ValueError("No refresh_token stored on connection")
    new_tokens = await _exchange_refresh_token(refresh, settings)
    merged = {**payload, **new_tokens}
    conn.oauth_tokens_encrypted = encrypt_tokens(json.dumps(merged), settings)
    await db.flush()
    return new_tokens
