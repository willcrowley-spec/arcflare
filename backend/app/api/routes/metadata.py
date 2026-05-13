from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select, tuple_

from app.api.deps import CurrentOrg, DbSession
from app.models.connection import PlatformConnection
from app.models.licensing import OrgLicenseSnapshot
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataField,
    MetadataObject,
    RecordTelemetry,
)
from app.schemas.common import PaginatedResponse
from app.schemas.metadata import (
    AutomationResponse,
    MetadataComponentResponse,
    MetadataFieldResponse,
    MetadataObjectResponse,
    MetadataSummary,
    TelemetryResponse,
    VelocityPoint,
)
from app.schemas.settings import ClassificationUpdate
from app.services.salesforce.telemetry import calculate_velocity

router = APIRouter()


@router.get("/summary", response_model=MetadataSummary)
async def get_metadata_summary(
    db: DbSession,
    org: CurrentOrg,
) -> MetadataSummary:
    obj_total = int(
        await db.scalar(
            select(func.count()).select_from(MetadataObject).where(MetadataObject.org_id == org.id)
        )
        or 0
    )
    obj_custom = int(
        await db.scalar(
            select(func.count()).select_from(MetadataObject).where(
                MetadataObject.org_id == org.id, MetadataObject.is_custom.is_(True)
            )
        )
        or 0
    )
    obj_with_records = int(
        await db.scalar(
            select(func.count()).select_from(MetadataObject).where(
                MetadataObject.org_id == org.id, MetadataObject.record_count > 0
            )
        )
        or 0
    )

    field_total = int(
        await db.scalar(
            select(func.count())
            .select_from(MetadataField)
            .join(MetadataObject, MetadataField.object_id == MetadataObject.id)
            .where(MetadataObject.org_id == org.id)
        )
        or 0
    )
    field_custom = int(
        await db.scalar(
            select(func.count())
            .select_from(MetadataField)
            .join(MetadataObject, MetadataField.object_id == MetadataObject.id)
            .where(MetadataObject.org_id == org.id, MetadataField.is_custom.is_(True))
        )
        or 0
    )

    auto_rows = await db.execute(
        select(MetadataAutomation.automation_type, func.count())
        .where(MetadataAutomation.org_id == org.id)
        .group_by(MetadataAutomation.automation_type)
    )
    auto_counts = {row[0]: row[1] for row in auto_rows.all()}

    comp_rows = await db.execute(
        select(MetadataComponent.component_category, func.count())
        .where(MetadataComponent.org_id == org.id)
        .group_by(MetadataComponent.component_category)
    )
    comp_counts = {row[0]: row[1] for row in comp_rows.all()}

    licensing: dict = {}
    license_snap = (
        await db.execute(
            select(OrgLicenseSnapshot)
            .where(OrgLicenseSnapshot.org_id == org.id)
            .order_by(OrgLicenseSnapshot.snapshot_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if license_snap:
        total_lic = sum(license_item.get("total", 0) for license_item in (license_snap.licenses_json or []))
        used_lic = sum(license_item.get("used", 0) for license_item in (license_snap.licenses_json or []))
        licensing = {
            "edition": license_snap.edition,
            "total_licenses": total_lic,
            "used_licenses": used_lic,
            "estimated_annual_spend": float(license_snap.estimated_annual_spend)
            if license_snap.estimated_annual_spend
            else None,
        }

    last_conn = (
        await db.execute(
            select(PlatformConnection)
            .where(PlatformConnection.org_id == org.id)
            .order_by(PlatformConnection.last_sync_at.desc().nulls_last())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_sync = last_conn.last_sync_at if last_conn else None

    return MetadataSummary(
        objects={"total": obj_total, "custom": obj_custom, "with_records": obj_with_records},
        fields={"total": field_total, "custom": field_custom},
        automations=auto_counts,
        components=comp_counts,
        licensing=licensing,
        last_sync_at=last_sync,
    )


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

    count_map: dict[tuple[UUID, str], int] = {}
    if rows:
        pairs = list({(r.connection_id, r.api_name) for r in rows})
        cnt_rows = await db.execute(
            select(
                MetadataAutomation.connection_id,
                MetadataAutomation.related_object,
                func.count(),
            )
            .where(
                MetadataAutomation.org_id == org.id,
                tuple_(MetadataAutomation.connection_id, MetadataAutomation.related_object).in_(pairs),
            )
            .group_by(MetadataAutomation.connection_id, MetadataAutomation.related_object)
        )
        for conn_id, related_object, cnt in cnt_rows.all():
            if related_object is not None:
                count_map[(conn_id, related_object)] = int(cnt or 0)

    items: list[MetadataObjectResponse] = []
    for r in rows:
        resp = MetadataObjectResponse.model_validate(r)
        resp.automation_count = count_map.get((r.connection_id, r.api_name), 0)
        items.append(resp)

    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.patch("/objects/{object_id}/classification", response_model=MetadataObjectResponse)
async def update_classification(
    object_id: UUID,
    body: ClassificationUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> MetadataObjectResponse:
    obj = await db.get(MetadataObject, object_id)
    if obj is None or obj.org_id != org.id:
        raise HTTPException(status_code=404, detail="Object not found")
    obj.classification = body.classification
    obj.classification_source = "manual"
    await db.commit()
    await db.refresh(obj)

    automation_count = await db.scalar(
        select(func.count()).select_from(MetadataAutomation).where(
            MetadataAutomation.related_object == obj.api_name,
            MetadataAutomation.connection_id == obj.connection_id,
        )
    )
    resp = MetadataObjectResponse.model_validate(obj)
    resp.automation_count = int(automation_count or 0)
    return resp


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


@router.get("/components", response_model=PaginatedResponse[MetadataComponentResponse])
async def list_components(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    component_category: str | None = None,
    q: str | None = None,
) -> PaginatedResponse[MetadataComponentResponse]:
    filters = [MetadataComponent.org_id == org.id]
    if component_category:
        filters.append(MetadataComponent.component_category == component_category)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(MetadataComponent.api_name.ilike(like), MetadataComponent.label.ilike(like))
        )
    total = int(
        await db.scalar(select(func.count()).select_from(MetadataComponent).where(*filters)) or 0
    )
    stmt = (
        select(MetadataComponent)
        .where(*filters)
        .order_by(MetadataComponent.api_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [MetadataComponentResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)
