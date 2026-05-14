from app.services.recommendations.financial_assumptions import (
    ASSUMPTION_MODEL_VERSION,
    build_financial_assumptions,
    classify_touchpoints,
)


def test_classify_touchpoints_keeps_salesforce_metadata_native():
    classified = classify_touchpoints(
        [
            "Salesforce Opportunity object (read/write)",
            "Opportunity_Ready_for_Invoicing_Automations flow",
            "QuickBooksInvoice__c object",
            "Opportunity_Record_Page component",
            "QuickBooks external accounting system API",
            "Calendly or scheduling integration for intake call booking",
        ]
    )

    assert classified["external_integrations"] == [
        "QuickBooks external accounting system API",
        "Calendly or scheduling integration for intake call booking",
    ]
    assert "Salesforce Opportunity object (read/write)" in classified["native_salesforce_touchpoints"]
    assert "Opportunity_Ready_for_Invoicing_Automations flow" in classified["native_salesforce_touchpoints"]
    assert "QuickBooksInvoice__c object" in classified["native_salesforce_touchpoints"]
    assert "Opportunity_Record_Page component" in classified["native_salesforce_touchpoints"]


def test_classify_touchpoints_treats_salesforce_object_api_as_native_not_external():
    classified = classify_touchpoints(
        [
            "Watcher__c and Contact object APIs",
            "Task object API for before-insert processing",
            "ActionItem__c object API",
            "Account_Invoices__cio and Account_Cases__cio Data Cloud object APIs",
            "Slack API via SlackActions Apex class",
            "Notification channel (email or Slack) for anomaly alerts",
        ]
    )

    assert classified["external_integrations"] == [
        "Slack API via SlackActions Apex class",
        "Notification channel (email or Slack) for anomaly alerts",
    ]
    assert "Watcher__c and Contact object APIs" in classified["native_salesforce_touchpoints"]
    assert "Task object API for before-insert processing" in classified["native_salesforce_touchpoints"]
    assert "ActionItem__c object API" in classified["native_salesforce_touchpoints"]
    assert (
        "Account_Invoices__cio and Account_Cases__cio Data Cloud object APIs"
        in classified["native_salesforce_touchpoints"]
    )


def test_build_financial_assumptions_uses_range_based_pilot_costs_and_preserves_overrides():
    assumptions = build_financial_assumptions(
        {
            "agent_type": "hybrid",
            "complexity_estimate": "high",
            "topics": [
                {"reasoning_type": "hybrid"},
                {"reasoning_type": "deterministic"},
            ],
            "integration_points": [
                "Salesforce Opportunity object (read/write)",
                "Salesforce Task object",
                "Opportunity_Record_Page component",
                "QuickBooks external accounting system API",
            ],
            "financial_signals": {
                "estimated_hours_per_week_saved": 12,
                "estimated_frequency": "daily",
                "estimated_actor_count": 3,
                "primary_role_type": "operations",
            },
        },
        existing_assumptions={"overrides": {"technology_cost": 12345}},
    )

    assert assumptions is not None
    assert assumptions["assumption_model_version"] == ASSUMPTION_MODEL_VERSION
    assert assumptions["overrides"] == {"technology_cost": 12345}
    assert assumptions["touchpoint_classification"]["external_integration_count"] == 1
    assert assumptions["touchpoint_classification"]["native_salesforce_touchpoint_count"] == 3
    assert assumptions["investment_components"]["external_integration"] == 4_000
    assert assumptions["investment_range"]["expected"] == assumptions["investment_range"]["pilot_mvp"]
    assert assumptions["investment_range"]["enterprise_hardened"] > assumptions["investment_range"]["expected"]
    assert assumptions["technology_cost"] < 30_000


def test_build_financial_assumptions_caps_actor_count_to_org_human_users():
    assumptions = build_financial_assumptions(
        {
            "agent_type": "hybrid",
            "complexity_estimate": "medium",
            "topics": [{"reasoning_type": "hybrid"}],
            "integration_points": [
                "User_Skill_Before_Create_Update flow",
                "UserSkillCertificationHandler Apex class",
            ],
            "financial_signals": {
                "actors_impacted": [
                    "User",
                    "System Automation: User_Skill_Before_Create_Update",
                    "System Automation: User_Certification_Before_Create_Update",
                    "UserSkillCertificationHandler",
                ],
                "estimated_hours_per_week_saved": 6,
                "estimated_frequency": "weekly",
                "estimated_actor_count": 50,
                "primary_role_type": "User",
            },
        },
        org_context={"human_users": 9, "business_entity_headcount": 10},
    )

    assert assumptions is not None
    assert assumptions["actor_count"] == 9
    assert assumptions["hours_basis"] == "team_total"
    assert assumptions["source_signals"]["estimated_actor_count"] == 50
    assert assumptions["source_signals"]["org_human_user_cap"] == 9
    assert "actor_count_capped_to_org_human_users" in assumptions["assumption_warnings"]
    assert "non_human_actor_labels_present" in assumptions["assumption_warnings"]
