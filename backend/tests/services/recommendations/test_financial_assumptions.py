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
