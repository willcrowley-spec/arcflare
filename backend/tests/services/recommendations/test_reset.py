from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.recommendation_run import RecommendationRun


ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
NEW_RUN_ID = UUID("00000000-0000-0000-0000-000000000002")


class _ScalarResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _FakeDb:
    def __init__(self, active_run=None, scalar_values=None):
        self.active_run = active_run
        self.scalar_values = list(scalar_values or [])
        self.executed = []
        self.scalar_statements = []
        self.added = None
        self.commits = 0
        self.flushes = 0
        self.refreshed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _ScalarResult(self.active_run)

    async def scalar(self, stmt):
        self.scalar_statements.append(stmt)
        return self.scalar_values.pop(0)

    def add(self, row):
        self.added = row

    async def flush(self):
        self.flushes += 1
        if self.added is not None:
            self.added.id = NEW_RUN_ID

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        self.refreshed.append(row)


@pytest.mark.asyncio
async def test_reset_recommendation_portfolio_deletes_all_statuses_and_queues_fresh_run(monkeypatch):
    from app.services.recommendations.reset import reset_recommendation_portfolio

    active_run = SimpleNamespace(status="running", completed_at=None)
    db = _FakeDb(
        active_run=active_run,
        scalar_values=[
            4,  # recommendations
            3,  # recommendation runs
            2,  # agent generation runs
            1,  # linked agents
        ],
    )
    queued = []
    monkeypatch.setattr(
        "app.services.recommendations.reset.generate_recommendations_task.delay",
        lambda org_id, run_id: queued.append((org_id, run_id)),
    )

    result = await reset_recommendation_portfolio(db, org_id=ORG_ID, rerun=True)

    assert active_run.status == "cancelled"
    assert isinstance(db.added, RecommendationRun)
    assert db.added.org_id == ORG_ID
    assert db.added.status == "pending"
    assert db.added.config["reset_reason"] == "clear_recommendation_portfolio"
    assert db.flushes == 1
    assert db.commits == 1
    assert db.refreshed == [db.added]
    assert queued == [(str(ORG_ID), str(NEW_RUN_ID))]
    assert result.recommendations_deleted == 4
    assert result.recommendation_runs_deleted == 3
    assert result.agent_generation_runs_deleted == 2
    assert result.agents_unlinked == 1
    assert result.queued_run_id == NEW_RUN_ID


@pytest.mark.asyncio
async def test_reset_recommendation_portfolio_can_clear_without_rerun(monkeypatch):
    from app.services.recommendations.reset import reset_recommendation_portfolio

    db = _FakeDb(scalar_values=[1, 1, 0, 0])
    queued = []
    monkeypatch.setattr(
        "app.services.recommendations.reset.generate_recommendations_task.delay",
        lambda org_id, run_id: queued.append((org_id, run_id)),
    )

    result = await reset_recommendation_portfolio(db, org_id=ORG_ID, rerun=False)

    assert db.added is None
    assert queued == []
    assert result.queued_run_id is None
