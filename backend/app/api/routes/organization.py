import csv
import io
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentOrg, DbSession
from app.models.connection import PlatformConnection
from app.models.entity import BusinessEntity
from app.models.licensing import OrgLicenseSnapshot, UserVelocitySnapshot
from app.schemas.common import PaginatedResponse
from app.schemas.organization import (
    CostModelResponse,
    EntityCreate,
    EntityResponse,
    EntityUpdate,
    HierarchyNode,
    HierarchyResponse,
    LicenseSnapshotResponse,
    OrgProfileResponse,
    UserVelocityResponse,
)
from app.schemas.settings import AnalysisConfig, AnalysisConfigUpdate
from app.services.entities.cost_model import calculate_cost_deflection, calculate_hires_deflected
from app.services.entities.profiler import build_hierarchy, sync_from_salesforce

router = APIRouter()


def _to_hierarchy_nodes(data: list[dict]) -> list[HierarchyNode]:
    out: list[HierarchyNode] = []
    for n in data:
        out.append(
            HierarchyNode(
                id=n["id"],
                name=n["name"],
                entity_type=n.get("entity_type"),
                children=_to_hierarchy_nodes(n.get("children") or []),
            )
        )
    return out


@router.get("/models")
async def get_model_catalog(org: CurrentOrg) -> dict:
    """Return available providers/models and per-operation effective model mapping."""
    from app.core.config import get_settings as get_app_settings
    from app.services.ai.operations import MODEL_OPERATIONS, OPERATION_GROUPS, PROVIDER_DEFAULTS, resolve_model

    settings = get_app_settings()
    org_config = org.analysis_config or {}

    providers = []
    provider_checks = [
        ("gemini", "GEMINI_API_KEY", "Google Gemini"),
        ("anthropic", "ANTHROPIC_API_KEY", "Anthropic"),
        ("openai", "OPENAI_API_KEY", "OpenAI"),
    ]
    for pid, key_attr, name in provider_checks:
        key_val = (getattr(settings, key_attr, "") or "").strip()
        if not key_val:
            continue
        models = []
        for tier_name, model_id in PROVIDER_DEFAULTS.get(pid, {}).items():
            models.append({"id": model_id, "model_id": model_id, "label": model_id, "tier_default": tier_name})
        providers.append({"id": pid, "name": name, "models": models})

    operations = []
    for op_id, meta in MODEL_OPERATIONS.items():
        if meta.get("tier") not in ("lite", "fast", "strong"):
            continue
        if op_id == "embedding":
            effective_model = f"gemini/{settings.EMBEDDING_MODEL}"
        else:
            effective_model = resolve_model(operation=op_id, model_config=org_config, tier=meta["tier"])
        effective_provider = effective_model.split("/")[0] if "/" in effective_model else "unknown"
        operations.append({
            "id": op_id,
            "label": meta["label"],
            "group": meta["group"],
            "group_label": OPERATION_GROUPS.get(meta["group"], meta["group"]),
            "description": meta["description"],
            "default_tier": meta["tier"],
            "thinking_budget": meta.get("thinking_budget", 0),
            "output_format": meta.get("output_format", "text"),
            "effective_model": effective_model,
            "effective_provider": effective_provider,
        })

    return {"providers": providers, "operations": operations}


@router.get("/settings", response_model=AnalysisConfig)
async def get_settings(org: CurrentOrg) -> AnalysisConfig:
    config = org.analysis_config or {}
    return AnalysisConfig(**config)


@router.patch("/settings", response_model=AnalysisConfig)
async def update_settings(
    body: AnalysisConfigUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> AnalysisConfig:
    config = dict(org.analysis_config or {})
    for k, v in body.model_dump(exclude_unset=True).items():
        config[k] = v
    org.analysis_config = config
    await db.commit()
    await db.refresh(org)
    return AnalysisConfig(**org.analysis_config)


class ProcessMapSettings(BaseModel):
    process_map_direction: str = "TB"
    process_map_default_state: str = "collapsed"


@router.get("/process-map-settings")
async def get_process_map_settings(org: CurrentOrg) -> ProcessMapSettings:
    s = org.settings_json or {}
    return ProcessMapSettings(
        process_map_direction=s.get("process_map_direction", "TB"),
        process_map_default_state=s.get("process_map_default_state", "collapsed"),
    )


@router.patch("/process-map-settings")
async def update_process_map_settings(
    body: ProcessMapSettings,
    db: DbSession,
    org: CurrentOrg,
) -> ProcessMapSettings:
    s = dict(org.settings_json or {})
    s["process_map_direction"] = body.process_map_direction
    s["process_map_default_state"] = body.process_map_default_state
    org.settings_json = s
    await db.commit()
    await db.refresh(org)
    return ProcessMapSettings(
        process_map_direction=s.get("process_map_direction", "TB"),
        process_map_default_state=s.get("process_map_default_state", "collapsed"),
    )


@router.post("/reanalyze")
async def reanalyze(
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str | int]:
    from app.services.classification import reanalyze_org

    count = await reanalyze_org(org.id, db)
    return {"status": "completed", "objects_reclassified": count}


@router.get("/profile", response_model=OrgProfileResponse)
async def get_org_profile(
    org: CurrentOrg,
) -> OrgProfileResponse:
    return OrgProfileResponse.model_validate(org)


@router.get("/hierarchy", response_model=HierarchyResponse)
async def get_hierarchy(
    db: DbSession,
    org: CurrentOrg,
) -> HierarchyResponse:
    data = await build_hierarchy(org.id, db)
    roots = _to_hierarchy_nodes(data.get("roots") or [])
    return HierarchyResponse(roots=roots)


@router.get("/entities", response_model=PaginatedResponse[EntityResponse])
async def list_entities(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[EntityResponse]:
    total = await db.scalar(
        select(func.count()).select_from(BusinessEntity).where(BusinessEntity.org_id == org.id)
    )
    total = int(total or 0)
    q = await db.execute(
        select(BusinessEntity)
        .where(BusinessEntity.org_id == org.id)
        .order_by(BusinessEntity.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = q.scalars().all()
    items = [EntityResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    body: EntityCreate,
    db: DbSession,
    org: CurrentOrg,
) -> EntityResponse:
    ent = BusinessEntity(
        org_id=org.id,
        name=body.name,
        entity_type=body.entity_type,
        parent_id=body.parent_id,
        department=body.department,
        title=body.title,
        role=body.role,
        headcount=body.headcount,
        is_active=body.is_active,
        salesforce_user_id=body.salesforce_user_id,
        cost_data_json={},
        metadata_json={},
    )
    db.add(ent)
    await db.commit()
    await db.refresh(ent)
    return EntityResponse.model_validate(ent)


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def patch_entity(
    entity_id: UUID,
    body: EntityUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> EntityResponse:
    ent = await db.get(BusinessEntity, entity_id)
    if ent is None or ent.org_id != org.id:
        raise HTTPException(status_code=404, detail="Entity not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ent, k, v)
    await db.commit()
    await db.refresh(ent)
    return EntityResponse.model_validate(ent)


@router.post("/import-csv", response_model=dict)
async def import_entities_csv(
    db: DbSession,
    org: CurrentOrg,
    file: UploadFile = File(...),
) -> dict[str, int]:
    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    for row in reader:
        name = (row.get("name") or row.get("Name") or "").strip()
        if not name:
            continue
        ent = BusinessEntity(
            org_id=org.id,
            name=name,
            entity_type=row.get("entity_type") or row.get("type"),
            department=row.get("department"),
            title=row.get("title"),
            role=row.get("role"),
            headcount=int(row.get("headcount") or 1),
            is_active=True,
            salesforce_user_id=row.get("salesforce_user_id"),
            cost_data_json={},
            metadata_json={},
        )
        db.add(ent)
        count += 1
    await db.commit()
    return {"imported": count}


@router.get("/cost-model", response_model=CostModelResponse)
async def get_cost_model(
    db: DbSession,
    org: CurrentOrg,
) -> CostModelResponse:
    annual = await calculate_cost_deflection(org.id, db)
    hires = await calculate_hires_deflected(org.id, db)
    return CostModelResponse(
        org_id=org.id,
        annual_cost_deflection=float(annual),
        hires_deflected=float(hires),
        assumptions={"model": "heuristic_v1"},
    )


@router.post("/sync-from-salesforce", status_code=status.HTTP_202_ACCEPTED)
async def sync_entities_from_salesforce(
    db: DbSession,
    org: CurrentOrg,
    connection_id: UUID = Query(...),
) -> dict[str, str]:
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    n = await sync_from_salesforce(org.id, connection_id, db)
    await db.commit()
    return {"status": "accepted", "records_touched": str(n)}


@router.get("/licensing", response_model=LicenseSnapshotResponse)
async def get_licensing(
    db: DbSession,
    org: CurrentOrg,
) -> LicenseSnapshotResponse:
    snap = (
        await db.execute(
            select(OrgLicenseSnapshot)
            .where(OrgLicenseSnapshot.org_id == org.id)
            .order_by(OrgLicenseSnapshot.snapshot_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snap is None:
        raise HTTPException(status_code=404, detail="No licensing snapshot available")
    return LicenseSnapshotResponse.model_validate(snap)


@router.get("/user-velocity", response_model=list[UserVelocityResponse])
async def get_user_velocity(
    db: DbSession,
    org: CurrentOrg,
    limit: int = Query(24, ge=1, le=100),
) -> list[UserVelocityResponse]:
    rows = (
        await db.execute(
            select(UserVelocitySnapshot)
            .where(UserVelocitySnapshot.org_id == org.id)
            .order_by(UserVelocitySnapshot.snapshot_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [UserVelocityResponse.model_validate(r) for r in rows]
