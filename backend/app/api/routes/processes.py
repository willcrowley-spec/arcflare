from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentOrg, DbSession
from app.models.discovery import ProcessHandoff
from app.models.process import BusinessProcess, ProcessEdge, ProcessNode
from app.schemas.process import (
    ProcessCreate,
    ProcessExportRequest,
    ProcessKpis,
    ProcessNodeUpdate,
    ProcessResponse,
    ProcessUpdate,
)
from app.services.processes.export import export_json, export_lucidchart, export_svg
from app.services.processes.graph import build_process_graph

router = APIRouter()


class ProcessListResponse(BaseModel):
    items: list[ProcessResponse]
    kpis: ProcessKpis


class NodeBulkUpdate(BaseModel):
    nodes: list[ProcessNodeUpdate]


@router.get("/", response_model=ProcessListResponse)
async def list_processes(
    db: DbSession,
    org: CurrentOrg,
) -> ProcessListResponse:
    q = await db.execute(
        select(BusinessProcess).where(BusinessProcess.org_id == org.id).order_by(BusinessProcess.name)
    )
    rows = q.scalars().all()
    items = [ProcessResponse.model_validate(r) for r in rows]

    total = await db.scalar(
        select(func.count()).select_from(BusinessProcess).where(BusinessProcess.org_id == org.id)
    )
    avg_eff = await db.scalar(
        select(func.avg(BusinessProcess.efficiency_score)).where(BusinessProcess.org_id == org.id)
    )
    draft_c = await db.scalar(
        select(func.count()).select_from(BusinessProcess).where(
            BusinessProcess.org_id == org.id,
            BusinessProcess.status == "draft",
        )
    )
    pub_c = await db.scalar(
        select(func.count()).select_from(BusinessProcess).where(
            BusinessProcess.org_id == org.id,
            BusinessProcess.status == "published",
        )
    )
    domain_c = await db.scalar(
        select(func.count()).select_from(BusinessProcess).where(
            BusinessProcess.org_id == org.id,
            BusinessProcess.level == "domain",
        )
    )
    review_c = await db.scalar(
        select(func.count()).select_from(BusinessProcess).where(
            BusinessProcess.org_id == org.id,
            BusinessProcess.needs_review == True,
        )
    )
    handoff_c = await db.scalar(
        select(func.count()).select_from(ProcessHandoff).where(
            ProcessHandoff.org_id == org.id,
        )
    )
    gap_c = await db.scalar(
        select(func.count()).select_from(ProcessHandoff).where(
            ProcessHandoff.org_id == org.id,
            ProcessHandoff.is_gap == True,
        )
    )
    kpis = ProcessKpis(
        total_processes=int(total or 0),
        avg_efficiency=float(avg_eff) if avg_eff is not None else None,
        draft_count=int(draft_c or 0),
        published_count=int(pub_c or 0),
        domain_count=int(domain_c or 0),
        needs_review_count=int(review_c or 0),
        handoff_count=int(handoff_c or 0),
        gap_count=int(gap_c or 0),
    )
    return ProcessListResponse(items=items, kpis=kpis)


@router.get("/{process_id}")
async def get_process(
    process_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    graph = await build_process_graph(process_id, db)
    return {"process": ProcessResponse.model_validate(proc).model_dump(), "graph": graph}


@router.post("/", response_model=ProcessResponse, status_code=status.HTTP_201_CREATED)
async def create_process(
    body: ProcessCreate,
    db: DbSession,
    org: CurrentOrg,
) -> ProcessResponse:
    proc = BusinessProcess(
        org_id=org.id,
        name=body.name,
        category=body.category,
        description=body.description,
        efficiency_score=None,
        automation_level=body.automation_level,
        status=body.status,
        source=body.source,
        sub_process_count=0,
        managed_asset_count=0,
        metadata_json={},
    )
    db.add(proc)
    await db.commit()
    await db.refresh(proc)
    return ProcessResponse.model_validate(proc)


@router.patch("/{process_id}", response_model=ProcessResponse)
async def patch_process(
    process_id: UUID,
    body: ProcessUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> ProcessResponse:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(proc, k, v)
    await db.commit()
    await db.refresh(proc)
    return ProcessResponse.model_validate(proc)


@router.put("/{process_id}/nodes", response_model=dict)
async def put_process_nodes(
    process_id: UUID,
    body: NodeBulkUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, int]:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    updated = 0
    for n in body.nodes:
        node = await db.get(ProcessNode, n.node_id)
        if node is None or node.process_id != process_id:
            continue
        node.position_x = n.position_x
        node.position_y = n.position_y
        if n.label is not None:
            node.label = n.label
        if n.subtitle is not None:
            node.subtitle = n.subtitle
        if n.metadata_json is not None:
            node.metadata_json = n.metadata_json
        updated += 1
    await db.commit()
    return {"updated": updated}


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_processes(
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str]:
    from app.workers.process_discovery import process_discovery_task

    process_discovery_task.delay(str(org.id))
    return {"status": "accepted"}


@router.post("/{process_id}/export")
async def export_process(
    process_id: UUID,
    body: ProcessExportRequest,
    db: DbSession,
    org: CurrentOrg,
):
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    if body.format == "json":
        return await export_json(process_id, db)
    if body.format == "svg":
        svg = await export_svg(process_id, db)
        return PlainTextResponse(svg, media_type="image/svg+xml")
    return await export_lucidchart(process_id, db)
