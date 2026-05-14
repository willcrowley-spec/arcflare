from app.services.recommendations.financial_engine import (
    compute_base_savings,
    compute_portfolio_projections,
    compute_projections,
)


def test_compute_projections_uses_investment_range_by_scenario():
    assumptions = {
        "fte_annual_cost": 80_000,
        "hours_per_week": 10,
        "actor_count": 2,
        "efficiency_gain": 0.5,
        "annual_operational_cost": 1_000,
        "productivity_dip": 0.05,
        "hard_savings_pct": 0.25,
        "discount_rate": 0.1,
        "adoption_ramp": [0.1, 0.5, 0.85, 0.95, 1.0],
        "investment_range": {
            "pilot_mvp": 12_000,
            "expected": 12_000,
            "enterprise_hardened": 35_000,
        },
        "overrides": {},
    }

    projections = compute_projections(assumptions, automation_type="hybrid")

    assert projections["optimistic"]["total_investment"] == 12_000
    assert projections["expected"]["total_investment"] == 12_000
    assert projections["conservative"]["total_investment"] == 35_000


def test_portfolio_projection_preserves_per_recommendation_automation_type_defaults():
    raw = compute_portfolio_projections(
        [
            {"_automation_type": "deterministic"},
            {"_automation_type": "agentic"},
        ]
    )
    deterministic = compute_projections({}, automation_type="deterministic")
    agentic = compute_projections({}, automation_type="agentic")

    assert raw["npv"]["expected"] == (
        deterministic["npv"]["expected"] + agentic["npv"]["expected"]
    )


def test_base_savings_treats_team_total_hours_as_already_aggregated():
    assumptions = {
        "fte_annual_cost": 75_000,
        "hours_per_week": 6,
        "hours_basis": "team_total",
        "actor_count": 50,
        "efficiency_gain": 0.9,
    }

    assert compute_base_savings(assumptions) == 10_125


def test_base_savings_keeps_legacy_per_actor_hours_when_explicit():
    assumptions = {
        "fte_annual_cost": 75_000,
        "hours_per_week": 6,
        "hours_basis": "per_actor",
        "actor_count": 50,
        "efficiency_gain": 0.9,
    }

    assert compute_base_savings(assumptions) == 506_250
