"""Tests for agent analyzer - output parsing, ID resolution, validation."""

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

    def test_parses_portfolio_candidates_v1_and_keeps_non_agent_findings(self):
        raw = {
            "schema_version": "portfolio_candidates_v1",
            "portfolio_candidates": [
                {
                    "candidate_name": "QuickBooks Sync Hardening",
                    "portfolio_category": "external_integration",
                    "recommended_build_path": "external_integration",
                    "description": "Harden deterministic QuickBooks invoice sync.",
                    "topics": [
                        {
                            "topic_name": "Invoice sync",
                            "description": "Map webhook payloads into Salesforce records.",
                            "reasoning_type": "deterministic",
                            "actions_needed": ["Validate payload"],
                        }
                    ],
                    "replaces": _valid_opportunity()["replaces"],
                    "trigger": "QuickBooks webhook",
                    "data_requirements": [],
                    "suggested_metadata_refs": [],
                    "integration_points": ["QuickBooks"],
                    "complexity_estimate": "medium",
                    "confidence": 0.7,
                    "rationale": "Valuable integration, not an agent.",
                    "risks": "Token handling.",
                    "financial_signals": _valid_opportunity()["financial_signals"],
                    "runtime_reasoning_required": False,
                }
            ],
        }

        result = parse_opportunity_response(raw)

        assert len(result["agent_opportunities"]) == 1
        parsed = result["agent_opportunities"][0]
        assert parsed["agent_name"] == "QuickBooks Sync Hardening"
        assert parsed["portfolio_category_v1"] == "external_integration"
        assert parsed["recommended_build_path"] == "external_integration"
        assert parsed["runtime_reasoning_required"] is False


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
