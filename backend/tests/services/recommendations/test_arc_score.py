from uuid import uuid4

from app.models.recommendation import Recommendation
from app.services.recommendations.arc_score import apply_arc_score, compute_arc_score


def _opportunity(**overrides):
    data = {
        "agent_name": "Case Intake Agent",
        "agent_type": "hybrid",
        "description": "Automates repetitive case intake and prepares complex exceptions for review.",
        "topics": [
            {
                "topic_name": "Classify Request",
                "description": "Classifies routine inbound requests.",
                "reasoning_type": "hybrid",
                "actions_needed": ["query case", "update case"],
            },
            {
                "topic_name": "Prepare Resolution",
                "description": "Stages the case with suggested next actions.",
                "reasoning_type": "deterministic",
                "actions_needed": ["update fields"],
            },
        ],
        "replaces": [
            {
                "process_id": str(uuid4()),
                "process_name": "Inbound Case Intake",
                "steps_replaced": ["Classify request", "Assign owner"],
                "step_ids": [str(uuid4()), str(uuid4())],
                "replacement_type": "partial",
            }
        ],
        "trigger": "New case created",
        "data_requirements": ["Case", "Account"],
        "integration_points": [],
        "complexity_estimate": "low",
        "confidence": 0.72,
        "rationale": "The work is repetitive, high-volume, and well bounded.",
        "risks": "Low risk; exceptions route to a human.",
        "financial_signals": {
            "actors_impacted": ["support_agent"],
            "estimated_hours_per_week_saved": 30,
            "estimated_frequency": "daily",
            "estimated_actor_count": 4,
            "primary_role_type": "support_agent",
        },
    }
    data.update(overrides)
    return data


def test_high_value_low_risk_recommendation_scores_ready():
    result = compute_arc_score(
        _opportunity(),
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[str(uuid4()), str(uuid4())],
        scenarios_json={"npv": {"expected": 240000}, "expected": {"npv": 240000}},
    )

    assert result["scoring_method"] == "rules_v1"
    assert result["decision"] == "ready"
    assert result["score"] >= 0.75
    assert result["dimensions"]["value"]["score"] >= 0.75
    assert result["dimensions"]["feasibility"]["score"] >= 0.75
    assert result["evidence_gaps"] == []


def test_low_evidence_recommendation_lands_in_review():
    opportunity = _opportunity(
        financial_signals={},
        data_requirements=[],
        confidence=0.91,
        replaces=[
            {
                "process_id": str(uuid4()),
                "process_name": "Inbound Case Intake",
                "steps_replaced": [],
                "step_ids": [],
                "replacement_type": "partial",
            }
        ],
    )

    result = compute_arc_score(
        opportunity,
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[],
        scenarios_json={},
    )

    assert result["decision"] == "review"
    assert result["score"] < 0.75
    assert "missing_linked_steps" in result["evidence_gaps"]
    assert "missing_financial_signals" in result["evidence_gaps"]


def test_high_risk_or_low_suitability_recommendation_does_not_advance():
    opportunity = _opportunity(
        complexity_estimate="high",
        integration_points=["ERP", "Billing", "Policy Admin", "Document Store"],
        risks="High-risk fraud prevention flow that requires human review and compliance approval.",
        confidence=0.95,
    )

    result = compute_arc_score(
        opportunity,
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[str(uuid4())],
        scenarios_json={"npv": {"expected": 400000}, "expected": {"npv": 400000}},
    )

    assert result["decision"] in {"defer", "blocked"}
    assert result["dimensions"]["suitability"]["score"] < 0.55
    assert result["dimensions"]["risk_inverse"]["score"] < 0.55


def test_llm_confidence_does_not_directly_determine_arc_score():
    opportunity = _opportunity(
        complexity_estimate="high",
        confidence=0.99,
        data_requirements=[],
        financial_signals={},
        integration_points=["ERP", "Billing", "Policy Admin"],
        risks="Unclear ownership, multiple integrations, and manual approval required.",
    )

    result = compute_arc_score(
        opportunity,
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[],
        scenarios_json={},
    )

    assert result["llm_confidence"] == 0.99
    assert result["score"] < 0.75
    assert result["decision"] != "ready"


def test_value_dimension_uses_sanitized_assumption_signals_when_available():
    result = compute_arc_score(
        _opportunity(
            financial_signals={
                "actors_impacted": ["User", "System Automation: User_Skill_Before_Create_Update"],
                "estimated_hours_per_week_saved": 6,
                "estimated_frequency": "weekly",
                "estimated_actor_count": 50,
                "primary_role_type": "user",
            }
        ),
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[str(uuid4())],
        scenarios_json={"expected": {"npv": 25_000}},
        assumptions_json={
            "hours_per_week": 6,
            "hours_basis": "team_total",
            "actor_count": 9,
        },
    )

    assert result["dimensions"]["value"]["signals"]["actor_count"] == 9
    assert result["dimensions"]["value"]["signals"]["hours_basis"] == "team_total"


def test_salesforce_native_touchpoints_do_not_count_as_external_integration_burden():
    native_heavy = _opportunity(
        complexity_estimate="medium",
        integration_points=[
            "Salesforce CampaignMember object (trigger source)",
            "Salesforce Lead object (read and write for assignment updates)",
            "Salesforce Contact object (read for context)",
            "Salesforce Task object (create for follow-up tasks)",
            "HubSpot_Inc__HubSpot_Intelligence__c object (read for lead score enrichment)",
            "Lead_After_Insert_Send_Website_Lead_Notification_Internal flow",
        ],
    )
    with_external = _opportunity(
        complexity_estimate="medium",
        integration_points=[
            "Salesforce CampaignMember object (trigger source)",
            "Salesforce Lead object (read and write for assignment updates)",
            "Slack API via SlackActions Apex class",
            "QuickBooks external accounting system API",
        ],
    )

    native_result = compute_arc_score(
        native_heavy,
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[str(uuid4())],
        scenarios_json={"expected": {"npv": 200000}},
    )
    external_result = compute_arc_score(
        with_external,
        linked_process_ids=[str(uuid4())],
        linked_step_ids=[str(uuid4())],
        scenarios_json={"expected": {"npv": 200000}},
    )

    assert native_result["dimensions"]["feasibility"]["signals"]["external_integration_count"] == 0
    assert native_result["dimensions"]["risk_inverse"]["signals"]["external_integration_count"] == 0
    assert external_result["dimensions"]["feasibility"]["signals"]["external_integration_count"] == 2
    assert native_result["dimensions"]["feasibility"]["score"] > external_result["dimensions"]["feasibility"]["score"]
    assert native_result["dimensions"]["risk_inverse"]["score"] > external_result["dimensions"]["risk_inverse"]["score"]


def test_apply_arc_score_sets_compatibility_fields_and_divergence_flag():
    rec = Recommendation(
        org_id=uuid4(),
        title="Risky Agent",
        description="Risky candidate",
        priority=None,
        category="service",
        estimated_roi=None,
        composite_score=None,
        status="active",
        analysis_inputs_json=[],
        actions_json=[],
        impact_json={},
        architecture_health_json={},
        linked_process_ids=[str(uuid4())],
        recommendation_type="agent_opportunity",
        automation_type="hybrid",
        assumptions_json={},
        scenarios_json={},
        enrichment_log=[],
        agent_opportunity_json=_opportunity(
            confidence=0.99,
            complexity_estimate="high",
            financial_signals={},
            risks="Human review required for compliance approval.",
        ),
        linked_step_ids=[],
        financial_evaluation_status="pending",
    )

    result = apply_arc_score(rec)

    assert rec.arc_score_json == result
    assert rec.base_score == result["score"]
    assert rec.composite_score == result["score"]
    assert rec.llm_score == 0.99
    assert rec.score_divergence_flag is True


def test_pipeline_recommendation_builder_applies_arc_score_fields():
    from app.services.recommendations.pipeline import _build_agent_recommendation

    process_id = str(uuid4())
    step_id = str(uuid4())
    opportunity = _opportunity(
        replaces=[
            {
                "process_id": process_id,
                "process_name": "Inbound Case Intake",
                "steps_replaced": ["Classify request"],
                "step_ids": [step_id],
                "replacement_type": "partial",
            }
        ]
    )
    rec = _build_agent_recommendation(
        opportunity,
        uuid4(),
        uuid4(),
        uuid4(),
        process_contexts=[
            {
                "id": process_id,
                "name": "Inbound Case Intake",
                "system_touchpoints": ["Case.Status"],
                "steps": [
                    {
                        "id": step_id,
                        "name": "Classify request",
                        "system_touchpoints": ["Account.Name"],
                    }
                ],
            }
        ],
        salesforce_metadata={
            "objects": [
                {"api_name": "Case", "fields": [{"api_name": "Status"}]},
                {"api_name": "Account", "fields": [{"api_name": "Name"}]},
            ]
        },
    )

    assert rec.arc_score_json["scoring_method"] == "rules_v1"
    assert rec.composite_score == rec.arc_score_json["score"]
    assert rec.base_score == rec.arc_score_json["score"]
    assert rec.llm_score == 0.72
    assert rec.agent_opportunity_json["metadata_bindings_v1"]["bindings"]
    assert rec.impact_json["metadata_binding_manifest_v1"]["schema_version"] == "metadata_binding_manifest_v1"
