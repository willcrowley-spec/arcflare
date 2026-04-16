"""Cost deflection modeling."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity


async def calculate_cost_deflection(org_id: UUID, db: AsyncSession) -> Decimal:
    """
    Estimate annualized cost deflection from automation using stored entity cost_data_json.

    TODO: replace heuristic with calibrated model from finance inputs.
    """
    res = await db.execute(select(BusinessEntity).where(BusinessEntity.org_id == org_id))
    entities = res.scalars().all()
    total = Decimal("0")
    for ent in entities:
        cost = (ent.cost_data_json or {}).get("annual_cost")
        if isinstance(cost, (int, float)):
            total += Decimal(str(cost))
    return total * Decimal("0.05")


async def calculate_hires_deflected(org_id: UUID, db: AsyncSession) -> Decimal:
    """Rough FTE equivalent implied by headcount and automation signals."""
    headcount = await db.scalar(
        select(func.coalesce(func.sum(BusinessEntity.headcount), 0)).where(
            BusinessEntity.org_id == org_id
        )
    )
    hc = Decimal(str(int(headcount or 0)))
    return (hc * Decimal("0.02")).quantize(Decimal("0.01"))
