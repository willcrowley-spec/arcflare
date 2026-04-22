"""Tests for domain context assembly (Phase 1) — pure logic, no DB."""

import pytest
from uuid import uuid4

from app.services.recommendations.domain_assembler import (
    build_actor_roster,
    build_touchpoint_inventory,
    serialize_domain_context,
    truncate_steps_for_token_budget,
)


def _fake_process(name, actors=None, touchpoints=None, steps=None):
    return {
        "id": str(uuid4()),
        "name": name,
        "level": "process",
        "description": f"Description of {name}",
        "narrative": None,
        "actors": actors or [],
        "trigger_conditions": [],
        "decision_logic": [],
        "system_touchpoints": touchpoints or [],
        "failure_modes": [],
        "value_classification": "BVA",
        "complexity_score": "medium",
        "automation_potential": "high",
        "estimated_duration": None,
        "estimated_frequency": None,
        "steps": steps or [],
    }


def _fake_step(name, actors=None, touchpoints=None):
    return {
        "id": str(uuid4()),
        "name": name,
        "level": "step",
        "actors": actors or [],
        "decision_logic": [],
        "trigger_conditions": [],
        "system_touchpoints": touchpoints or [],
        "failure_modes": [],
        "estimated_duration": "15min",
        "estimated_frequency": "daily",
        "sequencing": {},
        "value_classification": "NVA",
        "complexity_score": "low",
    }


class TestBuildActorRoster:
    def test_deduplicates_across_processes(self):
        procs = [
            _fake_process("Proc A", actors=["Sales Rep", "Manager"]),
            _fake_process("Proc B", actors=["Sales Rep", "Analyst"]),
        ]
        roster = build_actor_roster(procs)
        assert "Sales Rep" in roster
        assert len(roster["Sales Rep"]) == 2
        assert "Manager" in roster
        assert "Analyst" in roster

    def test_includes_step_level_actors(self):
        step = _fake_step("Step 1", actors=["Intern"])
        procs = [_fake_process("Proc A", actors=["Manager"], steps=[step])]
        roster = build_actor_roster(procs)
        assert "Intern" in roster
        assert "Proc A > Step 1" in roster["Intern"][0]

    def test_empty_actors(self):
        procs = [_fake_process("Proc A")]
        roster = build_actor_roster(procs)
        assert roster == {}


class TestBuildTouchpointInventory:
    def test_groups_by_object(self):
        procs = [
            _fake_process("Proc A", touchpoints=[
                "Lead.Status", "Lead.Rating", "Opportunity.StageName",
            ]),
        ]
        inventory = build_touchpoint_inventory(procs)
        assert "Lead" in inventory
        assert "Status" in inventory["Lead"]
        assert "Rating" in inventory["Lead"]
        assert "Opportunity" in inventory

    def test_handles_non_dotted_touchpoints(self):
        procs = [_fake_process("Proc A", touchpoints=["SomeSystem"])]
        inventory = build_touchpoint_inventory(procs)
        assert "SomeSystem" in inventory


class TestTruncateSteps:
    def test_keeps_all_when_under_limit(self):
        steps = [_fake_step(f"Step {i}") for i in range(5)]
        result = truncate_steps_for_token_budget(steps, max_steps=8)
        assert len(result) == 5

    def test_truncates_to_max(self):
        steps = [_fake_step(f"Step {i}") for i in range(12)]
        result = truncate_steps_for_token_budget(steps, max_steps=8)
        assert len(result) == 8


class TestSerializeDomainContext:
    def test_returns_complete_structure(self):
        domain = {"id": str(uuid4()), "name": "Sales Ops", "description": "desc", "narrative": None}
        procs = [_fake_process("Lead Qual", actors=["Rep"], touchpoints=["Lead.Status"])]
        handoffs = []
        result = serialize_domain_context(domain, procs, handoffs)
        assert result["domain"]["name"] == "Sales Ops"
        assert len(result["processes"]) == 1
        assert "actor_roster" in result
        assert "system_touchpoints_summary" in result
