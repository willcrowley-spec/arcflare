import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from pydantic import BaseModel

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)

_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched_at": None}
_JWKS_TTL_SECONDS = 3600


class CurrentUser(BaseModel):
    """Authenticated user extracted from Clerk JWT."""

    clerk_user_id: str
    email: str | None = None
    org_id: str | None = None
    raw_claims: dict[str, Any] = {}


def _get_fernet(settings: Settings) -> Fernet:
    key = settings.ENCRYPTION_KEY.strip()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as e:
        raise RuntimeError("ENCRYPTION_KEY must be a valid Fernet key") from e


def encrypt_tokens(plaintext: str, settings: Settings | None = None) -> bytes:
    settings = settings or get_settings()
    f = _get_fernet(settings)
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_tokens(ciphertext: bytes, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    f = _get_fernet(settings)
    try:
        return f.decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Could not decrypt token payload") from e


async def _fetch_jwks(jwks_url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        return resp.json()


def _resolve_jwks_url(settings: Settings) -> str:
    if settings.CLERK_JWKS_URL:
        return settings.CLERK_JWKS_URL
    if settings.CLERK_ISSUER:
        issuer = settings.CLERK_ISSUER.rstrip("/")
        return f"{issuer}/.well-known/jwks.json"
    raise RuntimeError("Configure CLERK_JWKS_URL or CLERK_ISSUER for JWT verification")


def _get_jwk_for_token(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise JWTError("Unable to find signing key")


async def verify_clerk_jwt(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """
    Decode and verify a Clerk-issued JWT using JWKS (RS256).
    """
    settings = settings or get_settings()
    jwks_url = _resolve_jwks_url(settings)

    now = datetime.now(tz=UTC).timestamp()
    cache_time = _JWKS_CACHE.get("fetched_at")
    if (
        _JWKS_CACHE.get("keys") is None
        or cache_time is None
        or now - cache_time > _JWKS_TTL_SECONDS
    ):
        jwks_data = await _fetch_jwks(jwks_url)
        _JWKS_CACHE["keys"] = jwks_data
        _JWKS_CACHE["fetched_at"] = now
    else:
        jwks_data = _JWKS_CACHE["keys"]

    jwk_dict = _get_jwk_for_token(token, jwks_data)
    public_key = jwk.construct(jwk_dict)

    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
    }
    if settings.CLERK_ISSUER:
        decode_kwargs["issuer"] = settings.CLERK_ISSUER
    pub = (settings.CLERK_PUBLISHABLE_KEY or "").strip()
    if pub:
        decode_kwargs["audience"] = pub

    try:
        claims = jwt.decode(token, public_key, **decode_kwargs)
    except JWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from e
    return claims


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    claims = await verify_clerk_jwt(credentials.credentials, settings)
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    org_id = (
        claims.get("org_id")
        or (claims.get("o") or {}).get("id")
        if isinstance(claims.get("o"), dict)
        else None
    )
    if org_id is None:
        org_role = claims.get("org_role")
        if isinstance(org_role, str) and ":" in org_role:
            org_id = org_role.split(":", 1)[0]

    return CurrentUser(
        clerk_user_id=sub,
        email=claims.get("email"),
        org_id=str(org_id) if org_id else None,
        raw_claims=claims,
    )


def parse_uuid(value: str | None, field_name: str = "id") -> UUID:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing {field_name}",
        )
    try:
        return UUID(value)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}",
        ) from e
