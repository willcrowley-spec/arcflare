from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentOrg, DbSession
from app.models.agent import Agent, AgentUsageLog
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
    AgentUpdate,
    AgentUsageResponse,
    FleetAnalyticsResponse,
    FleetKpis,
)
from app.schemas.common import PaginatedResponse

router = APIRouter()


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    kpis: FleetKpis


@router.get("/fleet-analytics", response_model=FleetAnalyticsResponse)
async def fleet_analytics(
    db: DbSession,
    org: CurrentOrg,
) -> FleetAnalyticsResponse:
    q = await db.execute(select(Agent).where(Agent.org_id == org.id))
    agents = q.scalars().all()
    by_status: dict[str, int] = {}
    by_model: dict[str, int] = {}
    total_spend = Decimal("0")
    total_tokens = 0
    total_tasks = 0
    active = 0
    for a in agents:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        if a.model:
            by_model[a.model] = by_model.get(a.model, 0) + 1
        total_spend += Decimal(str(a.total_spend or 0))
        total_tokens += int(a.total_tokens or 0)
        total_tasks += int(a.tasks_completed or 0)
        if a.status == "active":
            active += 1
    kpis = FleetKpis(
        total_agents=len(agents),
        active_agents=active,
        total_spend=total_spend,
        total_tokens=total_tokens,
        total_tasks=total_tasks,
    )
    return FleetAnalyticsResponse(kpis=kpis, by_status=by_status, by_model=by_model)


@router.get("/", response_model=AgentListResponse)
async def list_agents(
    db: DbSession,
    org: CurrentOrg,
) -> AgentListResponse:
    q = await db.execute(select(Agent).where(Agent.org_id == org.id).order_by(Agent.name))
    rows = q.scalars().all()
    items = [AgentResponse.model_validate(r) for r in rows]

    total = await db.scalar(select(func.count()).select_from(Agent).where(Agent.org_id == org.id))
    active = await db.scalar(
        select(func.count()).select_from(Agent).where(
            Agent.org_id == org.id,
            Agent.status == "active",
        )
    )
    spend = await db.scalar(
        select(func.coalesce(func.sum(Agent.total_spend), 0)).where(Agent.org_id == org.id)
    )
    tokens = await db.scalar(
        select(func.coalesce(func.sum(Agent.total_tokens), 0)).where(Agent.org_id == org.id)
    )
    tasks = await db.scalar(
        select(func.coalesce(func.sum(Agent.tasks_completed), 0)).where(Agent.org_id == org.id)
    )
    kpis = FleetKpis(
        total_agents=int(total or 0),
        active_agents=int(active or 0),
        total_spend=Decimal(str(spend or 0)),
        total_tokens=int(tokens or 0),
        total_tasks=int(tasks or 0),
    )
    return AgentListResponse(items=items, kpis=kpis)


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    db: DbSession,
    org: CurrentOrg,
) -> AgentResponse:
    agent = Agent(
        org_id=org.id,
        name=body.name,
        model=body.model,
        model_version=body.model_version,
        monthly_cap=body.monthly_cap,
        capability_tags=body.capability_tags or [],
        config_json=body.config_json or {},
        linked_recommendation_id=body.linked_recommendation_id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> AgentResponse:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.org_id != org.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def patch_agent(
    agent_id: UUID,
    body: AgentUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> AgentResponse:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.org_id != org.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(agent, k, v)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/usage", response_model=PaginatedResponse[AgentUsageResponse])
async def list_agent_usage(
    agent_id: UUID,
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[AgentUsageResponse]:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.org_id != org.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    total = await db.scalar(
        select(func.count()).select_from(AgentUsageLog).where(AgentUsageLog.agent_id == agent_id)
    )
    total = int(total or 0)
    q = await db.execute(
        select(AgentUsageLog)
        .where(AgentUsageLog.agent_id == agent_id)
        .order_by(AgentUsageLog.logged_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = q.scalars().all()
    items = [AgentUsageResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> None:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.org_id != org.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
