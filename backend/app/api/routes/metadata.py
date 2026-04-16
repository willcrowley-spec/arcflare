from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentOrg, DbSession
from app.models.metadata import MetadataAutomation, MetadataField, MetadataObject, RecordTelemetry
from app.schemas.common import PaginatedResponse
from app.schemas.metadata import (
    AutomationResponse,
    MetadataFieldResponse,
    MetadataObjectResponse,
    TelemetryResponse,
    VelocityPoint,
)
from app.services.salesforce.telemetry import calculate_velocity

router = APIRouter()


@router.get("/objects", response_model=PaginatedResponse[MetadataObjectResponse])
async def list_metadata_objects(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_custom: bool | None = None,
    q: str | None = None,
    connection_id: UUID | None = None,
) -> PaginatedResponse[MetadataObjectResponse]:
    filters = [MetadataObject.org_id == org.id]
    if is_custom is not None:
        filters.append(MetadataObject.is_custom.is_(is_custom))
    if connection_id is not None:
        filters.append(MetadataObject.connection_id == connection_id)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(MetadataObject.api_name.ilike(like), MetadataObject.label.ilike(like))
        )

    count_q = await db.execute(select(func.count()).select_from(MetadataObject).where(*filters))
    total = int(count_q.scalar_one() or 0)

    stmt = (
        select(MetadataObject)
        .where(*filters)
        .order_by(MetadataObject.api_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = [MetadataObjectResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/objects/{object_id}", response_model=MetadataObjectResponse)
async def get_metadata_object(
    object_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> MetadataObjectResponse:
    obj = await db.get(MetadataObject, object_id)
    if obj is None or obj.org_id != org.id:
        raise HTTPException(status_code=404, detail="Metadata object not found")
    return MetadataObjectResponse.model_validate(obj)


@router.get("/objects/{object_id}/telemetry", response_model=list[TelemetryResponse])
async def get_object_telemetry(
    object_id: UUID,
    db: DbSession,
    org: CurrentOrg,
    limit: int = Query(30, ge=1, le=500),
) -> list[TelemetryResponse]:
    obj = await db.get(MetadataObject, object_id)
    if obj is None or obj.org_id != org.id:
        raise HTTPException(status_code=404, detail="Metadata object not found")
    q = await db.execute(
        select(RecordTelemetry)
        .where(RecordTelemetry.object_id == object_id)
        .order_by(RecordTelemetry.snapshot_at.desc())
        .limit(limit)
    )
    rows = q.scalars().all()
    return [TelemetryResponse.model_validate(r) for r in rows]


@router.get("/objects/{object_id}/fields", response_model=list[MetadataFieldResponse])
async def get_object_fields(
    object_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> list[MetadataFieldResponse]:
    obj = await db.get(MetadataObject, object_id)
    if obj is None or obj.org_id != org.id:
        raise HTTPException(status_code=404, detail="Metadata object not found")
    q = await db.execute(
        select(MetadataField)
        .where(MetadataField.object_id == object_id)
        .order_by(MetadataField.api_name)
    )
    rows = q.scalars().all()
    return [MetadataFieldResponse.model_validate(r) for r in rows]


@router.get("/automation", response_model=PaginatedResponse[AutomationResponse])
async def list_automation(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[AutomationResponse]:
    filters = [MetadataAutomation.org_id == org.id]
    count_q = await db.execute(select(func.count()).select_from(MetadataAutomation).where(*filters))
    total = int(count_q.scalar_one() or 0)
    stmt = (
        select(MetadataAutomation)
        .where(*filters)
        .order_by(MetadataAutomation.api_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [AutomationResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/velocity", response_model=list[VelocityPoint])
async def get_velocity(
    db: DbSession,
    org: CurrentOrg,
    timeframe_days: int = Query(30, ge=1, le=365),
) -> list[VelocityPoint]:
    q = await db.execute(select(MetadataObject).where(MetadataObject.org_id == org.id))
    objs = q.scalars().all()
    out: list[VelocityPoint] = []
    for obj in objs:
        score = await calculate_velocity(obj.id, timeframe_days, db)
        out.append(
            VelocityPoint(
                object_id=obj.id,
                api_name=obj.api_name,
                velocity_score=score,
                window_days=timeframe_days,
            )
        )
    out.sort(key=lambda x: x.velocity_score, reverse=True)
    return out
