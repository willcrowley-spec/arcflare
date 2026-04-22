"""Tests for agent analyzer - output parsing, ID resolution, validation."""

import pytest
from uuid import uuid4

from app.services.recommendations.agent_analyzer import (
    parse_opportunity_response,
    resolve_ids,
    validate_opportunity,
)


SAMPLE_DOMAIN_CONTEXT = {
    "domain": {"id": str(uuid4()), "name": "Sales Ops"},
    "processes": [
        {
            "id": "aaaa-1111",
            "name": "Lead Qualification",
            "steps": [
                {"id": "bbbb-1111", "name": "BANT Scoring"},
                {"id": "bbbb-2222", "name": "Lead Rating"},
            ],
        },
        {
            "id": "aaaa-2222",
            "name": "Opportunity Creation",
            "steps": [
                {"id": "cccc-1111", "name": "Record Setup"},
            ],
        },
    ],
}


def _valid_opportunity():
    return {
        "agent_name": "Test Agent",
        "agent_type": "headless",
        "description": "Does stuff",
        "topics": [{"topic_name": "T1", "description": "d", "reasoning_type": "agentic", "actions_needed": []}],
        "replaces": [
            {
                "process_id": "aaaa-1111",
                "process_name": "Lead Qualification",
                "steps_replaced": ["BANT Scoring"],
                "step_ids": ["bbbb-1111"],
                "replacement_type": "partial",
            }
        ],
        "trigger": "Record event",
        "data_requirements": ["Lead"],
        "integration_points": [],
        "complexity_estimate": "medium",
        "confidence": 0.8,
        "rationale": "Good fit",
        "risks": "None",
        "financial_signals": {
            "actors_impacted": ["Rep"],
            "estimated_hours_per_week_saved": 5,
            "estimated_frequency": "daily",
            "estimated_actor_count": 2,
            "primary_role_type": "sales_operations",
        },
    }


class TestParseOpportunityResponse:
    def test_parses_valid_json(self):
        raw = {"agent_opportunities": [_valid_opportunity()], "uncovered_processes": []}
        result = parse_opportunity_response(raw)
        assert len(result["agent_opportunities"]) == 1

    def test_handles_missing_uncovered(self):
        raw = {"agent_opportunities": [_valid_opportunity()]}
        result = parse_opportunity_response(raw)
        assert result["uncovered_processes"] == []

    def test_filters_invalid_opportunities(self):
        bad = {"agent_name": "", "topics": []}
        raw = {"agent_opportunities": [_valid_opportunity(), bad]}
        result = parse_opportunity_response(raw)
        assert len(result["agent_opportunities"]) == 1


class TestValidateOpportunity:
    def test_valid_passes(self):
        assert validate_opportunity(_valid_opportunity()) is True

    def test_missing_name_fails(self):
        opp = _valid_opportunity()
        opp["agent_name"] = ""
        assert validate_opportunity(opp) is False

    def test_no_topics_fails(self):
        opp = _valid_opportunity()
        opp["topics"] = []
        assert validate_opportunity(opp) is False

    def test_no_replaces_fails(self):
        opp = _valid_opportunity()
        opp["replaces"] = []
        assert validate_opportunity(opp) is False


class TestResolveIds:
    def test_resolves_by_name_match(self):
        opp = _valid_opportunity()
        resolved = resolve_ids(opp, SAMPLE_DOMAIN_CONTEXT)
        replaces = resolved["replaces"][0]
        assert replaces["process_id"] == "aaaa-1111"
        assert "bbbb-1111" in replaces["step_ids"]

    def test_handles_unresolvable_step(self):
        opp = _valid_opportunity()
        opp["replaces"][0]["steps_replaced"] = ["Nonexistent Step"]
        opp["replaces"][0]["step_ids"] = []
        resolved = resolve_ids(opp, SAMPLE_DOMAIN_CONTEXT)
        assert resolved["replaces"][0]["step_ids"] == []
