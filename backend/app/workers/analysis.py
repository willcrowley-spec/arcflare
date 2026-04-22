from __future__ import annotations

import re
from uuid import UUID

from app.workers.celery_app import celery_app

# ---------------------------------------------------------------------------
# Financial assumption helpers (shared by worker task + API recalculate-all)
# ---------------------------------------------------------------------------

ROLE_SALARY: dict[str, int] = {
    "sales_operations": 70_000,
    "sales_representative": 75_000,
    "sales_development_representative": 65_000,
    "account_executive": 110_000,
    "account_manager": 85_000,
    "engineering": 130_000,
    "platform_engineer": 130_000,
    "software_engineer": 125_000,
    "sre": 130_000,
    "customer_support": 55_000,
    "support_agent": 55_000,
    "support_case_manager": 65_000,
    "technical_account_manager": 95_000,
    "finance_operations": 80_000,
    "finance_analyst": 80_000,
    "commission_manager": 85_000,
    "marketing": 90_000,
    "operations": 75_000,
    "operations_coordinator": 70_000,
    "product_manager": 110_000,
    "business_analyst": 85_000,
    "data_analyst": 80_000,
    "system_administrator": 85_000,
    "administrative_user": 55_000,
    "devops": 125_000,
    "architect": 140_000,
    "user": 75_000,
}

_ROLE_SUFFIX_STRIP = [
    "specialist", "analyst", "coordinator", "owner",
    "lead", "senior", "junior", "associate", "manager",
]

COMPLEXITY_TECH_COST = {"low": 8_000, "medium": 15_000, "high": 25_000}
INTEGRATION_COST_PER = 2_500


def normalize_role_salary(raw: str) -> int:
    """Map a freeform LLM role string to the closest ROLE_SALARY value."""
    s = re.sub(r"[^a-z0-9]+", "_", raw.lower().strip()).strip("_")
    if s in ROLE_SALARY:
        return ROLE_SALARY[s]

    for key, salary in ROLE_SALARY.items():
        if key in s or s in key:
            return salary

    base = s
    for suffix in _ROLE_SUFFIX_STRIP:
        base = base.replace(f"_{suffix}", "").strip("_")
    if base != s and base in ROLE_SALARY:
        return ROLE_SALARY[base]
    for key, salary in ROLE_SALARY.items():
        if key in base or base in key:
            return salary

    return 75_000


def derive_efficiency_gain(opp_json: dict) -> float:
    """Vary efficiency by agent type and replacement coverage."""
    agent_type = opp_json.get("agent_type", "hybrid")
    replaces = opp_json.get("replaces") or []
    full_count = sum(1 for r in replaces if r.get("replacement_type") == "full")
    total = len(replaces) or 1
    full_ratio = full_count / total
    base = {"headless": 0.90, "conversational": 0.50, "hybrid": 0.70}.get(agent_type, 0.65)
    return round(min(base + full_ratio * 0.10, 0.95), 2)


def build_financial_assumptions(opp_json: dict) -> dict | None:
    """Build financial assumptions from an agent opportunity JSON blob.

    Returns None if the opportunity lacks the required financial signals.
    """
    signals = opp_json.get("financial_signals")
    if not isinstance(signals, dict):
        return None
    hours = signals.get("estimated_hours_per_week_saved")
    if not hours or float(hours) <= 0:
        return None

    role_raw = signals.get("primary_role_type", "operations")
    fte_cost = normalize_role_salary(role_raw)
    actor_count = int(signals.get("estimated_actor_count", 1))
    complexity = (opp_json.get("complexity_estimate") or "medium").lower()
    integrations = len(opp_json.get("integration_points") or [])
    tech_cost = COMPLEXITY_TECH_COST.get(complexity, 15_000) + (integrations * INTEGRATION_COST_PER)

    topics = opp_json.get("topics") or []
    has_agentic = any(t.get("reasoning_type") in ("agentic", "hybrid") for t in topics)
    estimated_actions = max(len(topics) * 3, 5)
    frequency = (signals.get("estimated_frequency") or "daily").lower()
    invocations_per_month = {"daily": 22, "weekly": 4, "monthly": 1, "ad-hoc": 8}.get(frequency, 10)
    annual_op_cost = (
        estimated_actions * 0.10 * invocations_per_month * 12 * actor_count
        if has_agentic else 2000
    )

    return {
        "fte_annual_cost": fte_cost,
        "hours_per_week": float(hours),
        "frequency": frequency,
        "actor_count": actor_count,
        "role_type": role_raw.lower().strip(),
        "technology_cost": tech_cost,
        "change_management_factor": 0.35,
        "annual_operational_cost": round(annual_op_cost, 2),
        "adoption_ramp": [0.1, 0.5, 0.85, 0.95, 1.0],
        "productivity_dip": 0.05,
        "efficiency_gain": derive_efficiency_gain(opp_json),
        "hard_savings_pct": 0.25,
        "discount_rate": 0.10,
        "source": "auto_estimated",
        "overrides": {},
    }


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="recommendations.generate_recommendations")
def generate_recommendations_task(org_id: str, run_id: str | None = None) -> str:
    """Run the recommendation pipeline.

    Args:
        org_id: Organization UUID as string.
        run_id: Pre-created RecommendationRun UUID.  When provided the pipeline
            reuses that row instead of creating a new one (keeps the ID
            returned by ``POST /generate`` valid for status polling).
    """
    import asyncio

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span
    from app.services.recommendations.pipeline import run_recommendation_pipeline

    async def _run() -> str:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings

        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(_engine, expire_on_commit=False)
            async with factory() as session:
                result_id = await run_recommendation_pipeline(
                    UUID(org_id),
                    session,
                    existing_run_id=UUID(run_id) if run_id else None,
                )
                return str(result_id)
        finally:
            await _engine.dispose()

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("recommendation_pipeline", metadata={"org_id": org_id}):
                result_id = asyncio.run(_run())
        return result_id
    finally:
        flush_langfuse()


@celery_app.task(name="recommendations.evaluate_agent_financials")
def evaluate_agent_financials_task(org_id: str, run_id: str) -> str:
    """Async financial evaluation for agent opportunities (Phase 4).

    Reads financial_signals from each pending recommendation, assembles
    assumptions, runs compute_projections, writes back results.
    """
    import asyncio
    import logging

    from app.core.observability import flush_langfuse, langfuse_context, langfuse_span
    from app.services.recommendations.financial_engine import compute_projections

    logger = logging.getLogger(__name__)

    async def _run() -> str:
        from decimal import Decimal

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.models.recommendation import Recommendation

        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(_engine, expire_on_commit=False)
            async with factory() as session:
                q = await session.execute(
                    select(Recommendation).where(
                        Recommendation.org_id == UUID(org_id),
                        Recommendation.recommendation_run_id == UUID(run_id),
                        Recommendation.financial_evaluation_status == "pending",
                    )
                )
                recs = list(q.scalars().all())
                evaluated = 0
                for rec in recs:
                    try:
                        opp = rec.agent_opportunity_json or {}
                        assumptions = build_financial_assumptions(opp)
                        if assumptions is None:
                            rec.financial_evaluation_status = "skipped"
                            continue
                        automation_type = rec.automation_type or "hybrid"
                        projections = compute_projections(assumptions, automation_type=automation_type)
                        rec.assumptions_json = assumptions
                        rec.scenarios_json = projections
                        rec.estimated_roi = Decimal(str(projections["npv"]["expected"]))
                        rec.financial_evaluation_status = "completed"
                        evaluated += 1
                    except Exception:
                        logger.exception("financial_eval_failed rec=%s", rec.id)
                        rec.financial_evaluation_status = "failed"
                    if evaluated % 5 == 0:
                        await session.commit()
                await session.commit()
                return f"evaluated={evaluated} total={len(recs)}"
        finally:
            await _engine.dispose()

    try:
        with langfuse_context(org_id=org_id):
            with langfuse_span("financial_evaluation", metadata={"org_id": org_id, "run_id": run_id}):
                result = asyncio.run(_run())
        return result
    finally:
        flush_langfuse()
