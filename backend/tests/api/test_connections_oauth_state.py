from types import SimpleNamespace

import pytest

from app.api.routes.connections import (
    _build_oauth_state,
    _extract_salesforce_org_id,
    _parse_oauth_state,
)


def _settings():
    return SimpleNamespace(
        ENCRYPTION_KEY="state-secret",
        CLERK_SECRET_KEY="",
        SALESFORCE_CLIENT_SECRET="",
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
