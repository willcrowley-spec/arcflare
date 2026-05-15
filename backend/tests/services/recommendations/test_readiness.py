from uuid import uuid4

from app.models.recommendation import Recommendation
from app.services.recommendations.readiness import (
    build_recommendation_readiness,
    classify_opportunity,
)


def _base_opportunity(**overrides):
    data = {
        "agent_name": "Case Triage Agent",
        "agent_type": "hybrid",
        "description": "Classifies ambiguous inbound case text and recommends the next best action.",
        "topics": [
            {
                "topic_name": "Classify Case",
                "description": "Classifies unstructured case text and detects exceptions.",
                "reasoning_type": "agentic",
                "actions_needed": ["Read Case", "Update Case"],
            }
        ],
        "replaces": [
            {
                "process_id": str(uuid4()),
                "process_name": "Case Intake",
                "steps_replaced": ["Review case"],
                "step_ids": [str(uuid4())],
                "replacement_type": "partial",
            }
        ],
        "trigger": "New case",
        "data_requirements": ["Case description"],
        "integration_points": [],
        "complexity_estimate": "medium",
        "confidence": 0.8,
        "rationale": "The case text is ambiguous and requires classification judgment.",
        "risks": "Human review is needed for escalations.",
        "financial_signals": {
            "actors_impacted": ["Support Agent"],
            "estimated_hours_per_week_saved": 8,
            "estimated_frequency": "daily",
            "estimated_actor_count": 3,
            "primary_role_type": "support_agent",
        },
        "metadata_binding_manifest_v1": {
            "bindings": [
                {
                    "status": "validated",
                    "ref_type": "object",
                    "api_name": "Case",
                    "object_api_name": "Case",
                    "operation": "read",
                }
            ],
            "unresolved_bindings": [],
            "unresolved_external_dependencies": [],
            "quality_gates": {
                "agent_ready": True,
                "missing_evidence": [],
                "unresolved_external_dependencies": [],
            },
        },
    }
    data.update(overrides)
    return data


def test_quickbooks_sync_classifies_as_external_integration_not_agent():
    quickbooks = _base_opportunity(
        agent_name="QuickBooks Integration Orchestrator",
        description=(
            "Consolidates QuickBooks webhook processing, token refresh, invoice sync, "
            "payment sync, and customer sync into one deterministic integration service."
        ),
        topics=[
            {
                "topic_name": "Payment Event Processing",
                "description": "Maps QuickBooks payment webhook payloads into Salesforce records.",
                "reasoning_type": "deterministic",
                "actions_needed": ["Validate payload", "Create payment record"],
            },
            {
                "topic_name": "Invoice Event Processing",
                "description": "Creates invoice and line records from QuickBooks payloads.",
                "reasoning_type": "deterministic",
                "actions_needed": ["Validate payload", "Create invoice records"],
            },
        ],
        integration_points=["QuickBooks REST API", "Salesforce Flow webhook listeners"],
        rationale="Centralizes integration maintenance.",
    )

    result = classify_opportunity(quickbooks)

    assert result["candidate_type"] == "external_integration_candidate"
    assert result["portfolio_category"] == "automation_integration"
    assert result["agent_readiness_status"] == "not_agent"
    assert result["generate_agent_allowed"] is False
    assert "deterministic" in result["generate_agent_disabled_reason"].lower()


def test_agentic_case_triage_can_be_agent_ready_with_grounded_evidence():
    result = classify_opportunity(_base_opportunity())

    assert result["candidate_type"] == "agent_candidate"
    assert result["portfolio_category"] == "agent_candidate"
    assert result["agent_readiness_status"] == "ready"
    assert result["generate_agent_allowed"] is True
    assert result["recommended_next_action"] == "generate_agent"


def test_accepted_non_agent_recommendation_still_cannot_generate_agent():
    rec = Recommendation(
        org_id=uuid4(),
        title="QuickBooks Integration Orchestrator",
        description="Consolidates QuickBooks deterministic sync flows.",
        priority=None,
        category="external_integration_candidate",
        estimated_roi=None,
        composite_score=0.9,
        status="accepted",
        analysis_inputs_json=[],
        actions_json=[],
        impact_json={},
        architecture_health_json={},
        linked_process_ids=[str(uuid4())],
        recommendation_type="agent_opportunity",
        automation_type="deterministic",
        base_score=0.9,
        llm_score=0.95,
        llm_rationale=None,
        score_divergence_flag=False,
        assumptions_json={},
        scenarios_json={},
        enrichment_log=[],
        agent_opportunity_json=_base_opportunity(
            agent_name="QuickBooks Integration Orchestrator",
            description="Consolidates QuickBooks webhook sync and API payload mapping.",
            topics=[
                {
                    "topic_name": "Sync Payload",
                    "description": "Maps structured payloads to Salesforce records.",
                    "reasoning_type": "deterministic",
                    "actions_needed": ["Map payload"],
                }
            ],
            integration_points=["QuickBooks REST API"],
        ),
        arc_score_json={"decision": "ready", "score": 0.9},
        linked_step_ids=[str(uuid4())],
        financial_evaluation_status="completed",
    )

    envelope = build_recommendation_readiness(rec)

    assert envelope["generate_agent_allowed"] is False
    assert envelope["agent_readiness_status"] == "not_agent"
    assert envelope["portfolio_category"] == "automation_integration"
