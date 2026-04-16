from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentOrg, DbSession
from app.models.recommendation import Recommendation
from app.schemas.common import PaginatedResponse
from app.schemas.recommendation import (
    RecommendationResponse,
    RecommendationStatusUpdate,
    RecommendationSummary,
)
from app.workers.analysis import generate_recommendations_task

router = APIRouter()


@router.get("/summary", response_model=RecommendationSummary)
async def recommendation_summary(
    db: DbSession,
    org: CurrentOrg,
) -> RecommendationSummary:
    total = await db.scalar(
        select(func.count()).select_from(Recommendation).where(Recommendation.org_id == org.id)
    )
    active = await db.scalar(
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.org_id == org.id, Recommendation.status == "active")
    )
    implemented = await db.scalar(
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.org_id == org.id, Recommendation.status == "implemented")
    )
    avg_roi = await db.scalar(
        select(func.avg(Recommendation.estimated_roi)).where(Recommendation.org_id == org.id)
    )
    cnt = func.count().label("cnt")
    top_cat = await db.execute(
        select(Recommendation.category, cnt)
        .where(Recommendation.org_id == org.id, Recommendation.category.is_not(None))
        .group_by(Recommendation.category)
        .order_by(cnt.desc())
        .limit(1)
    )
    row = top_cat.first()
    top_category = row[0] if row else None
    return RecommendationSummary(
        total=int(total or 0),
        active=int(active or 0),
        implemented=int(implemented or 0),
        avg_roi=float(avg_roi) if avg_roi is not None else None,
        top_category=top_category,
    )


@router.get("/", response_model=PaginatedResponse[RecommendationResponse])
async def list_recommendations(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
) -> PaginatedResponse[RecommendationResponse]:
    filters = [Recommendation.org_id == org.id]
    if status_filter:
        filters.append(Recommendation.status == status_filter)
    if category:
        filters.append(Recommendation.category == category)

    total = await db.scalar(select(func.count()).select_from(Recommendation).where(*filters))
    total = int(total or 0)
    q = await db.execute(
        select(Recommendation)
        .where(*filters)
        .order_by(Recommendation.generated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = q.scalars().all()
    items = [RecommendationResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_recommendations(
    org: CurrentOrg,
) -> dict[str, str]:
    generate_recommendations_task.delay(str(org.id))
    return {"status": "queued", "org_id": str(org.id)}


@router.get("/{recommendation_id}", response_model=RecommendationResponse)
async def get_recommendation(
    recommendation_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> RecommendationResponse:
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None or rec.org_id != org.id:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return RecommendationResponse.model_validate(rec)


@router.patch("/{recommendation_id}/status", response_model=RecommendationResponse)
async def patch_recommendation_status(
    recommendation_id: UUID,
    body: RecommendationStatusUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> RecommendationResponse:
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None or rec.org_id != org.id:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.status = body.status
    await db.commit()
    await db.refresh(rec)
    return RecommendationResponse.model_validate(rec)
