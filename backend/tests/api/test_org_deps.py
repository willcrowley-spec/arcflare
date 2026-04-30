import pytest
from fastapi import HTTPException

from app.api.deps import get_current_org
from app.core.security import CurrentUser
from app.models.organization import Organization


class _ScalarResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _FakeDb:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = None
        self.commits = 0
        self.refreshed = []

    async def execute(self, _stmt):
        return _ScalarResult(self.existing)

    def add(self, row):
        self.added = row

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        self.refreshed.append(row)


@pytest.mark.asyncio
async def test_get_current_org_creates_org_from_active_clerk_org():
    db = _FakeDb()
    user = CurrentUser(clerk_user_id="user_1", org_id="org_1", org_name="Acme")

    org = await get_current_org(db, user)

    assert org is db.added
    assert org.clerk_org_id == "org_1"
    assert org.name == "Acme"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_get_current_org_updates_placeholder_name_from_claim():
    existing = Organization(clerk_org_id="org_1", name="org_1")
    db = _FakeDb(existing)
    user = CurrentUser(clerk_user_id="user_1", org_id="org_1", org_name="Acme")

    org = await get_current_org(db, user)

    assert org is existing
    assert org.name == "Acme"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_get_current_org_rejects_missing_org_context():
    db = _FakeDb()
    user = CurrentUser(clerk_user_id="user_1")

    with pytest.raises(HTTPException) as exc:
        await get_current_org(db, user)

    assert exc.value.status_code == 403
