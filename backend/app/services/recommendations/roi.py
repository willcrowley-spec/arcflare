"""Deprecated legacy ROI estimation helper.

The active path uses ``financial_assumptions.py`` plus ``financial_engine.py``
through the centralized ``recompute.py`` boundary.
"""

from decimal import Decimal

from app.models.recommendation import Recommendation
from app.schemas.organization import CostModelResponse


def calculate_roi(
    recommendation: Recommendation,
    org_cost_model: CostModelResponse | dict,
) -> Decimal | None:
    """
    Combine recommendation impact with org cost model to estimate ROI.

    TODO: enrich with staffing costs and automation lift curves.
    """
    base = recommendation.composite_score or 0.0
    if isinstance(org_cost_model, CostModelResponse):
        lift = org_cost_model.annual_cost_deflection or 0.0
    else:
        lift = float(org_cost_model.get("annual_cost_deflection") or 0.0)
    if lift <= 0:
        return None
    return Decimal(str(round(base * lift, 2)))
