from types import SimpleNamespace
from uuid import UUID
from unittest.mock import patch

import pytest

from app.models.agent_design import AgentDesignPackage, AgentGenerationRun
from app.models.recommendation import Recommendation
from app.services.agent_design.workflow import regenerate_design_package


ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = UUID("00000000-0000-0000-0000-000000000002")
REC_ID = UUID("00000000-0000-0000-0000-000000000003")
DESIGN_ID = UUID("00000000-0000-0000-0000-000000000004")


class _ScalarResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _FakeDb:
    def __init__(self, run, recommendation, latest_design, source_bundle=None):
        self.run = run
        self.recommendation = recommendation
        self.results = [_ScalarResult(latest_design), _ScalarResult(source_bundle)]
        self.added = None
        self.commits = 0
        self.refreshed = []

    async def get(self, model, row_id):
        if model is AgentGenerationRun and row_id == RUN_ID:
            return self.run
        if model is Recommendation and row_id == REC_ID:
            return self.recommendation
        return None

    async def execute(self, _stmt):
        return self.results.pop(0)

    def add(self, row):
        self.added = row

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        self.refreshed.append(row)


@pytest.mark.asyncio
async def test_regenerate_design_package_creates_new_version_and_supersedes_blocked_design():
    run = SimpleNamespace(id=RUN_ID, org_id=ORG_ID, recommendation_id=REC_ID, status="blocked")
    recommendation = SimpleNamespace(id=REC_ID, org_id=ORG_ID)
    latest_design = SimpleNamespace(
        id=DESIGN_ID,
        org_id=ORG_ID,
        generation_run_id=RUN_ID,
        recommendation_id=REC_ID,
        status="blocked",
        version=1,
    )
    db = _FakeDb(run, recommendation, latest_design)

    with (
        patch("app.services.agent_design.workflow.assemble_generation_context", return_value={"ctx": True}),
        patch(
            "app.services.agent_design.workflow.build_design_package_from_context",
            return_value={"schema_version": "agent_design_package_v1", "blockers": []},
        ),
        patch("app.services.agent_design.workflow._known_objects", return_value={"User_Skill__c"}),
        patch("app.services.agent_design.workflow.validate_design_package", return_value={"blockers": [], "warnings": []}),
    ):
        regenerated = await regenerate_design_package(db, org_id=ORG_ID, run_id=RUN_ID)

    assert regenerated is run
    assert latest_design.status == "superseded"
    assert isinstance(db.added, AgentDesignPackage)
    assert db.added.version == 2
    assert db.added.status == "draft"
    assert run.status == "awaiting_review"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_regenerate_design_package_rejects_source_generated_runs():
    run = SimpleNamespace(id=RUN_ID, org_id=ORG_ID, recommendation_id=REC_ID, status="source_generated")
    recommendation = SimpleNamespace(id=REC_ID, org_id=ORG_ID)
    latest_design = SimpleNamespace(
        id=DESIGN_ID,
        org_id=ORG_ID,
        generation_run_id=RUN_ID,
        recommendation_id=REC_ID,
        status="source_generated",
        version=1,
    )
    db = _FakeDb(run, recommendation, latest_design, source_bundle=SimpleNamespace(id="source"))

    with pytest.raises(ValueError) as exc:
        await regenerate_design_package(db, org_id=ORG_ID, run_id=RUN_ID)

    assert str(exc.value) == "design_package_not_repairable"
    assert latest_design.status == "source_generated"
    assert db.added is None
