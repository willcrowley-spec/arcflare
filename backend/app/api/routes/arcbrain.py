from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentOrg, DbSession
from app.schemas.arcbrain import (
    ArcbrainBlastRadiusResponse,
    ArcbrainNode,
    ArcbrainReplacementHeatResponse,
    ArcbrainSearchResponse,
    ArcbrainSnapshotResponse,
)
from app.services.arcbrain.projection import ArcbrainProjectionService

router = APIRouter()
service = ArcbrainProjectionService()


@router.get("/snapshot", response_model=ArcbrainSnapshotResponse)
async def get_arcbrain_snapshot(
    db: DbSession,
    org: CurrentOrg,
) -> ArcbrainSnapshotResponse:
    return await service.snapshot(org.id, db)


@router.get("/search", response_model=ArcbrainSearchResponse)
async def search_arcbrain(
    db: DbSession,
    org: CurrentOrg,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(25, ge=1, le=100),
) -> ArcbrainSearchResponse:
    snapshot = await service.snapshot(org.id, db)
    return service.search(snapshot, q, limit=limit)


@router.get("/node/{node_id}", response_model=ArcbrainNode)
async def get_arcbrain_node(
    node_id: str,
    db: DbSession,
    org: CurrentOrg,
) -> ArcbrainNode:
    snapshot = await service.snapshot(org.id, db)
    node = service.get_node(snapshot, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Arcbrain node not found")
    return node


@router.get("/blast-radius/{node_id}", response_model=ArcbrainBlastRadiusResponse)
async def get_arcbrain_blast_radius(
    node_id: str,
    db: DbSession,
    org: CurrentOrg,
    depth: int = Query(1, ge=1, le=4),
) -> ArcbrainBlastRadiusResponse:
    snapshot = await service.snapshot(org.id, db)
    try:
        return service.blast_radius(snapshot, node_id, depth=depth)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Arcbrain node not found") from exc


@router.get("/replacement-heat", response_model=ArcbrainReplacementHeatResponse)
async def get_arcbrain_replacement_heat(
    db: DbSession,
    org: CurrentOrg,
) -> ArcbrainReplacementHeatResponse:
    snapshot = await service.snapshot(org.id, db)
    return service.replacement_heat(snapshot)
