from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.connections import (
    _build_oauth_state,
    _extract_salesforce_org_id,
    _parse_oauth_state,
    _salesforce_authorization_error,
    router,
)
from app.core.database import get_db


def _settings():
    return SimpleNamespace(
        ENCRYPTION_KEY="state-secret",
        CLERK_SECRET_KEY="",
        SALESFORCE_CLIENT_SECRET="",
        FRONTEND_URL="https://frontend.test",
    )


def test_oauth_state_round_trip_preserves_org_user_and_action():
    state = _build_oauth_state(
        {
            "action": "connect",
            "clerk_org_id": "org_123",
            "clerk_user_id": "user_123",
        },
        _settings(),
    )

    payload = _parse_oauth_state(state, _settings())

    assert payload["action"] == "connect"
    assert payload["clerk_org_id"] == "org_123"
    assert payload["clerk_user_id"] == "user_123"
    assert isinstance(payload["ts"], int)


def test_oauth_state_rejects_tampering():
    state = _build_oauth_state({"action": "connect", "clerk_org_id": "org_123"}, _settings())
    body, sig = state.split(".", 1)
    replacement = "A" if body[-1] != "A" else "B"
    tampered = f"{body[:-1]}{replacement}.{sig}"

    with pytest.raises(ValueError):
        _parse_oauth_state(tampered, _settings())


def test_extract_salesforce_org_id_from_identity_url():
    tokens = {"id": "https://login.salesforce.com/id/00Dxx000000001A/005xx000000001B"}

    assert _extract_salesforce_org_id(tokens) == "00Dxx000000001A"


def test_salesforce_authorization_error_maps_cross_org_block():
    assert _salesforce_authorization_error("OAUTH_AUTHORIZATION_BLOCKED") == (
        "salesforce_authorization_blocked"
    )


def _callback_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.core import config as config_module

    monkeypatch.setattr(config_module, "get_settings", _settings)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/connections")

    async def _db_override():
        yield object()

    app.dependency_overrides[get_db] = _db_override
    return TestClient(app)


def test_salesforce_callback_redirects_authorization_errors(monkeypatch: pytest.MonkeyPatch):
    client = _callback_client(monkeypatch)

    response = client.get(
        "/api/v1/connections/salesforce/callback?error=access_denied&state=opaque",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://frontend.test/#/analysis?connection_error=salesforce_access_denied"
    )


def test_salesforce_callback_redirects_missing_code(monkeypatch: pytest.MonkeyPatch):
    client = _callback_client(monkeypatch)

    response = client.get(
        "/api/v1/connections/salesforce/callback?state=opaque",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://frontend.test/#/analysis?connection_error=missing_authorization_code"
    )
