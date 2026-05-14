from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.agent_design import AgentGenerationRun
from app.models.recommendation import Recommendation
from app.models.recommendation_run import RecommendationRun
from app.workers.analysis import generate_recommendations_task


@dataclass(frozen=True)
class RecommendationPortfolioResetResult:
    recommendations_deleted: int
    recommendation_runs_deleted: int
    agent_generation_runs_deleted: int
    agents_unlinked: int
    queued_run_id: UUID | None


async def _count(db: AsyncSession, model, *filters) -> int:
    value = await db.scalar(select(func.count()).select_from(model).where(*filters))
    return int(value or 0)


async def reset_recommendation_portfolio(
    db: AsyncSession,
    *,
    org_id: UUID,
    rerun: bool = True,
) -> RecommendationPortfolioResetResult:
    """Clear generated recommendation state for an org and optionally queue a fresh run.

    This is intentionally scoped to the recommendation/Agent Builder surface. It does not
    remove Salesforce connections, metadata inventory, process maps, documents, users, or orgs.
    """
    active_run_q = await db.execute(
        select(RecommendationRun)
        .where(
            RecommendationRun.org_id == org_id,
            RecommendationRun.status.in_(["running", "pending"]),
        )
        .order_by(RecommendationRun.started_at.desc())
        .limit(1)
    )
    active_run = active_run_q.scalar_one_or_none()
    if active_run is not None:
        active_run.status = "cancelled"
        active_run.completed_at = datetime.now(tz=UTC)

    recommendations_deleted = await _count(db, Recommendation, Recommendation.org_id == org_id)
    recommendation_runs_deleted = await _count(
        db,
        RecommendationRun,
        RecommendationRun.org_id == org_id,
    )
    agent_generation_runs_deleted = await _count(
        db,
        AgentGenerationRun,
        AgentGenerationRun.org_id == org_id,
    )
    agents_unlinked = await _count(
        db,
        Agent,
        Agent.org_id == org_id,
        Agent.linked_recommendation_id.is_not(None),
    )

    await db.execute(
        update(Agent)
        .where(Agent.org_id == org_id, Agent.linked_recommendation_id.is_not(None))
        .values(linked_recommendation_id=None)
    )
    await db.execute(delete(AgentGenerationRun).where(AgentGenerationRun.org_id == org_id))
    await db.execute(delete(Recommendation).where(Recommendation.org_id == org_id))
    await db.execute(delete(RecommendationRun).where(RecommendationRun.org_id == org_id))

    queued_run: RecommendationRun | None = None
    if rerun:
        queued_run = RecommendationRun(
            org_id=org_id,
            status="pending",
            config={
                "reset_reason": "clear_recommendation_portfolio",
                "queued_after_reset_at": datetime.now(tz=UTC).isoformat(),
            },
        )
        db.add(queued_run)
        await db.flush()

    await db.commit()

    if queued_run is not None:
        await db.refresh(queued_run)
        generate_recommendations_task.delay(str(org_id), str(queued_run.id))

    return RecommendationPortfolioResetResult(
        recommendations_deleted=recommendations_deleted,
        recommendation_runs_deleted=recommendation_runs_deleted,
        agent_generation_runs_deleted=agent_generation_runs_deleted,
        agents_unlinked=agents_unlinked,
        queued_run_id=queued_run.id if queued_run is not None else None,
    )
