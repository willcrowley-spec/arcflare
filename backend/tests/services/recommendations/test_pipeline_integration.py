"""Integration smoke tests for the agent opportunity pipeline."""



def test_pipeline_imports():
    """Verify all pipeline modules import without errors."""
    from app.services.recommendations.domain_assembler import assemble_domain_contexts
    from app.services.recommendations.agent_analyzer import analyze_domain
    from app.services.recommendations.cross_domain import synthesize_cross_domain
    from app.services.recommendations.pipeline import run_recommendation_pipeline
    from app.services.recommendations.financial_engine import compute_projections
    from app.workers.analysis import evaluate_agent_financials_task

    assert callable(assemble_domain_contexts)
    assert callable(analyze_domain)
    assert callable(synthesize_cross_domain)
    assert callable(run_recommendation_pipeline)
    assert callable(compute_projections)
    assert evaluate_agent_financials_task.name == "recommendations.evaluate_agent_financials"


def test_domain_assembler_helpers():
    """Verify pure helpers work end-to-end."""
    from app.services.recommendations.domain_assembler import (
        build_actor_roster,
        build_touchpoint_inventory,
        serialize_domain_context,
    )

    procs = [{
        "name": "Test Process",
        "actors": ["Admin", "User"],
        "system_touchpoints": ["Account.Name", "Contact.Email"],
        "steps": [{
            "name": "Step 1",
            "actors": ["User"],
            "system_touchpoints": ["Account.Industry"],
        }],
    }]

    roster = build_actor_roster(procs)
    assert "Admin" in roster
    assert "User" in roster
    assert len(roster["User"]) == 2

    inventory = build_touchpoint_inventory(procs)
    assert "Account" in inventory
    assert "Name" in inventory["Account"]
    assert "Industry" in inventory["Account"]
    assert "Contact" in inventory

    ctx = serialize_domain_context(
        {"id": "x", "name": "Test", "description": None, "narrative": None},
        procs,
        [],
    )
    assert ctx["domain"]["name"] == "Test"
    assert len(ctx["processes"]) == 1
    assert "actor_roster" in ctx


def test_agent_analyzer_parsing():
    """Verify opportunity parsing and validation work end-to-end."""
    from app.services.recommendations.agent_analyzer import (
        parse_opportunity_response,
        validate_opportunity,
    )

    valid_opp = {
        "agent_name": "Test Agent",
        "agent_type": "headless",
        "description": "Does stuff",
        "topics": [{"topic_name": "T", "description": "d", "reasoning_type": "agentic", "actions_needed": []}],
        "replaces": [{"process_id": "abc", "process_name": "P", "steps_replaced": [], "step_ids": [], "replacement_type": "full"}],
        "trigger": "event",
        "data_requirements": [],
        "integration_points": [],
        "complexity_estimate": "medium",
        "confidence": 0.8,
        "rationale": "test",
        "risks": "none",
        "financial_signals": {
            "actors_impacted": [],
            "estimated_hours_per_week_saved": 5,
            "estimated_frequency": "daily",
            "estimated_actor_count": 1,
            "primary_role_type": "operations",
        },
    }

    assert validate_opportunity(valid_opp) is True
    assert validate_opportunity({"agent_name": "", "topics": []}) is False

    result = parse_opportunity_response({"agent_opportunities": [valid_opp]})
    assert len(result["agent_opportunities"]) == 1


def test_pipeline_rejects_recommendation_with_fabricated_process_ids():
    from app.services.recommendations.pipeline import normalize_opportunity_replacements

    opportunity = {
        "agent_name": "Unified Lead Processing Agent",
        "replaces": [
            {
                "process_id": "lead_ingestion_web",
                "process_name": "Web Lead Ingestion Automation",
                "steps_replaced": ["Web Form Capture"],
                "step_ids": ["SF1"],
            }
        ],
    }
    process_contexts = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Actual Lead Intake",
            "steps": [
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "Capture inbound lead",
                }
            ],
        }
    ]

    assert normalize_opportunity_replacements(opportunity, process_contexts) is None


def test_pipeline_normalizes_leaf_process_as_step_evidence():
    from app.services.recommendations.pipeline import normalize_opportunity_replacements

    process_id = "11111111-1111-1111-1111-111111111111"
    opportunity = {
        "agent_name": "QuickBooks Invoice Backfill",
        "replaces": [
            {
                "process_id": process_id,
                "process_name": "QuickBooks Invoice Creation and Synchronization",
                "steps_replaced": [],
                "step_ids": [],
            }
        ],
    }
    process_contexts = [
        {
            "id": process_id,
            "name": "QuickBooks Invoice Creation and Synchronization",
            "steps": [],
        }
    ]

    normalized = normalize_opportunity_replacements(opportunity, process_contexts)

    assert normalized is not None
    assert normalized["replaces"][0]["process_id"] == process_id
    assert normalized["replaces"][0]["step_ids"] == [process_id]
