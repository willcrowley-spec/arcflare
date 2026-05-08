from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.process import BusinessProcess
from app.services.processes.domain_graph import get_domain_graph


ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
DOMAIN_ID = UUID("00000000-0000-0000-0000-000000000010")
PROCESS_ID = UUID("00000000-0000-0000-0000-000000000020")
STEP_A_ID = UUID("00000000-0000-0000-0000-000000000030")
STEP_B_ID = UUID("00000000-0000-0000-0000-000000000040")
HANDOFF_ID = UUID("00000000-0000-0000-0000-000000000050")


class _MappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDomainGraphDb:
    def __init__(self, domain, descendants, handoffs):
        self.domain = domain
        self.descendants = descendants
        self.handoffs = handoffs

    async def get(self, model, row_id):
        assert model is BusinessProcess
        assert row_id == DOMAIN_ID
        return self.domain

    async def execute(self, stmt, params=None):
        if params is not None:
            assert params == {"domain_id": str(DOMAIN_ID), "org_id": str(ORG_ID)}
            return _MappingResult(self.descendants)
        return _ScalarResult(self.handoffs)


@pytest.mark.asyncio
async def test_domain_graph_returns_enriched_nodes_edges_and_saved_positions():
    domain = SimpleNamespace(
        id=DOMAIN_ID,
        org_id=ORG_ID,
        level="domain",
        name="Revenue Operations",
        domain_map_positions={str(STEP_A_ID): {"x": 320, "y": 140}},
    )
    descendants = [
        {
            "id": PROCESS_ID,
            "name": "Lead Intake",
            "parent_id": DOMAIN_ID,
            "level": "process",
            "status": "discovered",
            "confidence_score": 0.82,
            "needs_review": False,
            "description": "Capture inbound demand.",
            "actors": [{"name": "Sales Ops", "type": "user"}],
            "system_touchpoints": [{"object_api_name": "Lead", "fields": ["Status"]}],
            "evidence_sources": [{"type": "metadata_object", "api_name": "Lead"}],
            "value_classification": "BVA",
            "automation_potential": "medium",
        },
        {
            "id": STEP_A_ID,
            "name": "Capture Lead",
            "parent_id": PROCESS_ID,
            "level": "step",
            "status": "discovered",
            "confidence_score": 0.91,
            "needs_review": False,
            "description": "Create or update the lead record.",
            "actors": [{"name": "Sales Rep", "type": "user"}],
            "system_touchpoints": [{"object_api_name": "Lead", "fields": ["Email"]}],
            "evidence_sources": [{"type": "automation", "api_name": "Lead_Capture"}],
            "value_classification": "VA",
            "automation_potential": "high",
        },
        {
            "id": STEP_B_ID,
            "name": "Qualify Lead",
            "parent_id": PROCESS_ID,
            "level": "step",
            "status": "discovered",
            "confidence_score": 0.64,
            "needs_review": True,
            "description": "Decide whether the lead should advance.",
            "actors": [{"name": "BDR", "type": "user"}],
            "system_touchpoints": [{"object_api_name": "Lead", "fields": ["Rating"]}],
            "evidence_sources": [{"type": "document_chunk", "document_name": "Lead SOP"}],
            "value_classification": "BVA",
            "automation_potential": "medium",
        },
    ]
    handoff = SimpleNamespace(
        id=HANDOFF_ID,
        source_process_id=STEP_A_ID,
        target_process_id=STEP_B_ID,
        handoff_type="manual",
        description="Rep reviews lead details before qualification.",
        confidence_score=0.58,
        is_gap=True,
        gap_status="open",
        needs_review=True,
        metadata_json={
            "data_transferred": [{"object": "Lead", "fields": ["Email", "Rating"]}],
            "transfer_mechanism": "manual review",
        },
        evidence_sources=[{"type": "document_chunk", "document_name": "Lead SOP"}],
    )

    result = await get_domain_graph(
        DOMAIN_ID,
        ORG_ID,
        _FakeDomainGraphDb(domain, descendants, [handoff]),
    )

    assert result["positions"] == {str(STEP_A_ID): {"x": 320, "y": 140}}

    process = result["hierarchy"][0]
    assert process["actors"] == [{"name": "Sales Ops", "type": "user"}]
    assert process["system_touchpoints"] == [{"object_api_name": "Lead", "fields": ["Status"]}]
    assert process["evidence_sources"] == [{"type": "metadata_object", "api_name": "Lead"}]
    assert process["value_classification"] == "BVA"
    assert process["automation_potential"] == "medium"

    step = process["children"][0]
    assert step["actors"] == [{"name": "Sales Rep", "type": "user"}]
    assert step["automation_potential"] == "high"

    assert result["edges"] == [
        {
            "id": str(HANDOFF_ID),
            "source_id": str(STEP_A_ID),
            "target_id": str(STEP_B_ID),
            "label": "manual",
            "description": "Rep reviews lead details before qualification.",
            "kind": "handoff",
            "confidence_score": 0.58,
            "is_gap": True,
            "gap_status": "open",
            "needs_review": True,
            "evidence_sources": [{"type": "document_chunk", "document_name": "Lead SOP"}],
            "data_transferred": [{"object": "Lead", "fields": ["Email", "Rating"]}],
            "transfer_mechanism": "manual review",
        }
    ]
