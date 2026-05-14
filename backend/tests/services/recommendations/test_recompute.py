from uuid import uuid4

from app.models.recommendation import Recommendation
from app.services.recommendations.recompute import recompute_recommendation


def _recommendation() -> Recommendation:
    return Recommendation(
        org_id=uuid4(),
        title="Payment Processing Agent",
        description="Automates payment processing exceptions.",
        priority=None,
        category="hybrid",
        estimated_roi=None,
        composite_score=0.91,
        status="active",
        analysis_inputs_json=[],
        actions_json=[],
        impact_json={},
        architecture_health_json={},
        linked_process_ids=[str(uuid4())],
        recommendation_type="agent_opportunity",
        automation_type="hybrid",
        base_score=None,
        llm_score=None,
        llm_rationale="Strong opportunity",
        score_divergence_flag=False,
        assumptions_json={"overrides": {"actor_count": 2}},
        scenarios_json={},
        enrichment_log=[],
        agent_opportunity_json={
            "agent_name": "Payment Processing Agent",
            "agent_type": "hybrid",
            "description": "Automates payment processing exceptions.",
            "topics": [{"topic_name": "Resolve", "reasoning_type": "hybrid"}],
            "replaces": [
                {
                    "process_id": str(uuid4()),
                    "process_name": "Payment Processing",
                    "step_ids": [str(uuid4())],
                    "replacement_type": "partial",
                }
            ],
            "data_requirements": ["Payment__c"],
            "integration_points": [
                "Salesforce fw1__Payment__c object",
                "QuickBooks external accounting system API",
            ],
            "complexity_estimate": "medium",
            "confidence": 0.93,
            "risks": "Exceptions route to a human.",
            "financial_signals": {
                "estimated_hours_per_week_saved": 15,
                "estimated_frequency": "daily",
                "estimated_actor_count": 4,
                "primary_role_type": "finance_operations",
            },
        },
        linked_step_ids=[str(uuid4())],
        financial_evaluation_status="pending",
    )


def test_recompute_populates_arc_score_and_preserves_user_overrides():
    rec = _recommendation()

    result = recompute_recommendation(rec)

    assert result["financial_status"] == "completed"
    assert rec.assumptions_json["overrides"] == {"actor_count": 2}
    assert rec.assumptions_json["touchpoint_classification"]["external_integration_count"] == 1
    assert rec.arc_score_json["scoring_method"] == "rules_v1"
    assert rec.arc_score_json["dimensions"]
    assert rec.base_score == rec.arc_score_json["score"]
    assert rec.composite_score == rec.arc_score_json["score"]
    assert rec.llm_score == 0.93
    assert rec.scenarios_json["expected"]["total_investment"] == rec.assumptions_json["investment_range"]["expected"]


def test_recompute_applies_new_overrides_and_recomputes_score():
    rec = _recommendation()

    recompute_recommendation(rec, overrides={"technology_cost": 999})

    assert rec.assumptions_json["overrides"]["actor_count"] == 2
    assert rec.assumptions_json["overrides"]["technology_cost"] == 999
    assert rec.scenarios_json["expected"]["total_investment"] == 999
    assert rec.arc_score_json["score"] == rec.composite_score
