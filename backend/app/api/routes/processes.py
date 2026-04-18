from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
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
from app.services.chat.actions import format_gap_handoff_item
from app.services.processes.export import export_json, export_lucidchart, export_svg
from app.services.processes.graph import build_process_graph
from app.services.processes.domain_graph import get_domain_graph

router = APIRouter()


class GapUpdateRequest(BaseModel):
    gap_status: str | None = Field(default=None, max_length=30)
    resolution_note: str | None = None


class ProcessListResponse(BaseModel):
    items: list[ProcessResponse]
    kpis: ProcessKpis
    tree: list[dict] = []


class NodeBulkUpdate(BaseModel):
    nodes: list[ProcessNodeUpdate]


@router.get("/gaps")
async def list_gaps(db: DbSession, org: CurrentOrg) -> dict:
    q = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org.id,
            ProcessHandoff.is_gap == True,
        )
    )
    rows = q.scalars().all()
    items = [await format_gap_handoff_item(h, db) for h in rows]
    return {"items": items, "total": len(items)}


@router.patch("/gaps/{handoff_id}")
async def update_gap(
    handoff_id: UUID,
    body: GapUpdateRequest,
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    row = await db.get(ProcessHandoff, handoff_id)
    if row is None or row.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap handoff not found")
    if body.gap_status is not None:
        row.gap_status = body.gap_status
    if body.resolution_note is not None:
        row.resolution_note = body.resolution_note
    await db.commit()
    await db.refresh(row)
    return await format_gap_handoff_item(row, db)


@router.get("/", response_model=ProcessListResponse)
async def list_processes(
    db: DbSession,
    org: CurrentOrg,
) -> ProcessListResponse:
    q = await db.execute(
        select(BusinessProcess).where(BusinessProcess.org_id == org.id).order_by(BusinessProcess.name)
    )
    all_rows = q.scalars().all()

    by_id: dict[UUID, ProcessResponse] = {}
    children_map: dict[UUID | None, list[ProcessResponse]] = {}
    for r in all_rows:
        resp = ProcessResponse.model_validate(r)
        by_id[r.id] = resp
        children_map.setdefault(r.parent_id, []).append(resp)

    def attach_children(item: ProcessResponse) -> dict:
        d = item.model_dump()
        kids = children_map.get(item.id, [])
        d["children"] = [attach_children(c) for c in kids]
        return d

    roots = children_map.get(None, [])
    items_tree = [attach_children(r) for r in roots]
    items_flat = [ProcessResponse.model_validate(r) for r in all_rows]

    total = len(all_rows)
    draft_c = sum(1 for r in all_rows if r.status == "draft")
    pub_c = sum(1 for r in all_rows if r.status == "published")
    domain_c = sum(1 for r in all_rows if r.level == "domain")
    review_c = sum(1 for r in all_rows if r.needs_review)
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
        total_processes=total,
        draft_count=draft_c,
        published_count=pub_c,
        domain_count=domain_c,
        needs_review_count=review_c,
        handoff_count=int(handoff_c or 0),
        gap_count=int(gap_c or 0),
    )
    return ProcessListResponse(items=items_flat, kpis=kpis, tree=items_tree)


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


@router.get("/{domain_id}/domain-graph")
async def get_domain_graph_endpoint(
    domain_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    """Return the full recursive hierarchy and edges for a domain."""
    try:
        return await get_domain_graph(domain_id, org.id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{domain_id}/domain-graph/positions")
async def save_domain_positions(
    domain_id: UUID,
    body: dict,
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    """Persist manual position overrides for the domain map."""
    proc = await db.get(BusinessProcess, domain_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Domain not found")
    proc.domain_map_positions = body.get("positions", {})
    await db.commit()
    return {"status": "ok"}


@router.delete("/{domain_id}/domain-graph/positions")
async def clear_domain_positions(
    domain_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    """Clear saved position overrides (reset layout)."""
    proc = await db.get(BusinessProcess, domain_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Domain not found")
    proc.domain_map_positions = {}
    await db.commit()
    return {"status": "ok"}


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
