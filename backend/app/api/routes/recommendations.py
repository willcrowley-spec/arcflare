from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Numeric, cast, func, select

from app.api.deps import CurrentOrg, DbSession
from app.models.recommendation import Recommendation
from app.models.recommendation_run import RecommendationRun
from app.schemas.common import PaginatedResponse
from app.schemas.recommendation import (
    PortfolioProjectionRequest,
    PortfolioProjectionResponse,
    RecalculateRequest,
    RecommendationResponse,
    RecommendationRunResponse,
    RecommendationStatusUpdate,
    RecommendationSummary,
)
from app.services.recommendations.financial_engine import (
    compute_portfolio_projections,
    compute_projections,
)
from app.workers.analysis import generate_recommendations_task

router = APIRouter()

_SORTABLE = {
    "composite_score": Recommendation.composite_score,
    "generated_at": Recommendation.generated_at,
    "estimated_roi": Recommendation.estimated_roi,
    "title": Recommendation.title,
    "priority": Recommendation.priority,
}


def _parse_sort(sort: str) -> tuple[str, bool]:
    sort = sort.strip()
    if sort.startswith("-"):
        return sort[1:], True
    return sort, False


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
    avg_npv = await db.scalar(
        select(
            func.avg(cast(Recommendation.scenarios_json["expected"]["npv"].astext, Numeric))
        ).where(Recommendation.org_id == org.id)
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

    by_type_rows = await db.execute(
        select(Recommendation.automation_type, func.count())
        .where(Recommendation.org_id == org.id)
        .group_by(Recommendation.automation_type)
    )
    by_automation_type = {r[0]: int(r[1]) for r in by_type_rows.all()}
    if not by_automation_type:
        by_automation_type = None

    return RecommendationSummary(
        total=int(total or 0),
        active=int(active or 0),
        implemented=int(implemented or 0),
        avg_roi=float(avg_roi) if avg_roi is not None else None,
        avg_npv=float(avg_npv) if avg_npv is not None else None,
        top_category=top_category,
        by_automation_type=by_automation_type,
    )


@router.get("/runs", response_model=PaginatedResponse[RecommendationRunResponse])
async def list_recommendation_runs(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[RecommendationRunResponse]:
    filters = [RecommendationRun.org_id == org.id]
    total = await db.scalar(select(func.count()).select_from(RecommendationRun).where(*filters))
    total = int(total or 0)
    q = await db.execute(
        select(RecommendationRun)
        .where(*filters)
        .order_by(RecommendationRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = q.scalars().all()
    items = [RecommendationRunResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/runs/{run_id}", response_model=RecommendationRunResponse)
async def get_recommendation_run(
    run_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> RecommendationRunResponse:
    run = await db.get(RecommendationRun, run_id)
    if run is None or run.org_id != org.id:
        raise HTTPException(status_code=404, detail="Recommendation run not found")
    return RecommendationRunResponse.model_validate(run)


@router.post("/portfolio-projection", response_model=PortfolioProjectionResponse)
async def portfolio_projection(
    body: PortfolioProjectionRequest,
    db: DbSession,
    org: CurrentOrg,
) -> PortfolioProjectionResponse:
    assumptions_list: list[dict] = []
    rec_rows: list[Recommendation] = []
    for rid in body.recommendation_ids:
        rec = await db.get(Recommendation, rid)
        if rec is None or rec.org_id != org.id:
            raise HTTPException(status_code=404, detail=f"Recommendation not found: {rid}")
        rec_rows.append(rec)
        assumptions_list.append(dict(rec.assumptions_json) if rec.assumptions_json else {})

    raw = compute_portfolio_projections(assumptions_list, body.global_overrides or None)
    by_automation_type: dict[str, int] = {}
    for rec in rec_rows:
        t = rec.automation_type or "hybrid"
        by_automation_type[t] = by_automation_type.get(t, 0) + 1

    return PortfolioProjectionResponse(
        optimistic=raw["optimistic"],
        expected=raw["expected"],
        conservative=raw["conservative"],
        npv=raw["npv"],
        payback_month=raw["payback_month"],
        recommendation_count=raw["recommendation_count"],
        by_automation_type=by_automation_type,
    )


@router.get("/", response_model=PaginatedResponse[RecommendationResponse])
async def list_recommendations(
    db: DbSession,
    org: CurrentOrg,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    recommendation_type: str | None = None,
    automation_type: str | None = None,
    sort: str = Query("-composite_score", description="Field name, prefix - for descending"),
) -> PaginatedResponse[RecommendationResponse]:
    filters = [Recommendation.org_id == org.id]
    if status_filter:
        filters.append(Recommendation.status == status_filter)
    if category:
        filters.append(Recommendation.category == category)
    if recommendation_type:
        filters.append(Recommendation.recommendation_type == recommendation_type)
    if automation_type:
        filters.append(Recommendation.automation_type == automation_type)

    sort_field, sort_desc = _parse_sort(sort)
    col = _SORTABLE.get(sort_field, Recommendation.composite_score)
    if sort_field not in _SORTABLE:
        sort_desc = True

    total = await db.scalar(select(func.count()).select_from(Recommendation).where(*filters))
    total = int(total or 0)
    stmt = (
        select(Recommendation).where(*filters).offset((page - 1) * page_size).limit(page_size)
    )
    if sort_desc:
        stmt = stmt.order_by(col.desc().nullslast())
    else:
        stmt = stmt.order_by(col.asc().nullslast())

    q = await db.execute(stmt)
    rows = q.scalars().all()
    items = [RecommendationResponse.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


STALE_RUNNING_SECONDS = 600


@router.get("/status")
async def recommendation_pipeline_status(
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    """Return the latest RecommendationRun status for the org (used for polling).

    Includes a staleness check: if the run has been ``running`` or ``pending``
    for longer than ``STALE_RUNNING_SECONDS`` without completing, we flip it to
    ``failed`` so the frontend stops polling and the user can retry.
    """
    q = await db.execute(
        select(RecommendationRun)
        .where(RecommendationRun.org_id == org.id)
        .order_by(RecommendationRun.started_at.desc())
        .limit(1)
    )
    run = q.scalar_one_or_none()
    if run is None:
        return {"status": "idle", "run_id": None, "error": None, "stage_results": {}}

    run_status = run.status
    if run_status in ("running", "pending") and run.started_at:
        elapsed = (datetime.now(tz=UTC) - run.started_at).total_seconds()
        if elapsed > STALE_RUNNING_SECONDS:
            run.status = "failed"
            run.error = (
                f"Pipeline timed out — no completion after {int(elapsed)}s. "
                "The worker may have restarted. Click Generate to retry."
            )
            run.completed_at = datetime.now(tz=UTC)
            await db.commit()
            await db.refresh(run)
            run_status = run.status

    config = run.config or {}
    return {
        "status": run_status,
        "run_id": str(run.id),
        "error": run.error,
        "stage_results": run.stage_results or {},
        "current_stage": config.get("current_stage"),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_recommendations(
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str]:
    existing = await db.execute(
        select(RecommendationRun)
        .where(
            RecommendationRun.org_id == org.id,
            RecommendationRun.status.in_(["running", "pending"]),
        )
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A recommendation pipeline is already running. Cancel it first or wait for it to finish.",
        )

    run = RecommendationRun(org_id=org.id, status="pending", config={})
    db.add(run)
    await db.commit()
    await db.refresh(run)

    generate_recommendations_task.delay(str(org.id), str(run.id))
    return {"status": "queued", "org_id": str(org.id), "run_id": str(run.id)}


@router.post("/cancel")
async def cancel_recommendation_pipeline(
    db: DbSession,
    org: CurrentOrg,
) -> dict[str, str]:
    """Cancel the latest running/pending recommendation pipeline."""
    q = await db.execute(
        select(RecommendationRun)
        .where(
            RecommendationRun.org_id == org.id,
            RecommendationRun.status.in_(["running", "pending"]),
        )
        .order_by(RecommendationRun.started_at.desc())
        .limit(1)
    )
    run = q.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="No active pipeline to cancel")
    run.status = "cancelled"
    run.completed_at = datetime.now(tz=UTC)
    await db.commit()
    return {"status": "cancelled", "run_id": str(run.id)}


@router.post("/{recommendation_id}/recalculate", response_model=RecommendationResponse)
async def recalculate_recommendation(
    recommendation_id: UUID,
    body: RecalculateRequest,
    db: DbSession,
    org: CurrentOrg,
) -> RecommendationResponse:
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None or rec.org_id != org.id:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    assumptions = dict(rec.assumptions_json) if rec.assumptions_json else {}
    overrides = dict(assumptions.get("overrides", {}))
    overrides.update(body.overrides)
    assumptions["overrides"] = overrides
    rec.assumptions_json = assumptions

    projections = compute_projections(
        assumptions, automation_type=rec.automation_type
    )
    previous_roi = rec.estimated_roi
    new_npv = projections["npv"]["expected"]
    rec.scenarios_json = projections
    rec.estimated_roi = Decimal(str(new_npv))

    log = list(rec.enrichment_log or [])
    log.append(
        {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "source": "api",
            "changes": dict(body.overrides),
            "roi_impact": {
                "before": float(previous_roi) if previous_roi is not None else None,
                "after": float(new_npv),
            },
        }
    )
    rec.enrichment_log = log

    await db.commit()
    await db.refresh(rec)
    return RecommendationResponse.model_validate(rec)


@router.post("/recalculate-all")
async def recalculate_all_recommendations(
    db: DbSession,
    org: CurrentOrg,
) -> dict:
    """Recalculate financial projections for ALL recommendations (any status) using current engine."""
    import logging
    logger = logging.getLogger(__name__)

    q = await db.execute(
        select(Recommendation).where(Recommendation.org_id == org.id)
    )
    recs = list(q.scalars().all())
    logger.info("recalculate_all org=%s found=%d recommendations", org.id, len(recs))
    updated = 0
    errors = 0
    for rec in recs:
        try:
            assumptions = dict(rec.assumptions_json) if rec.assumptions_json else {}
            projections = compute_projections(assumptions, automation_type=rec.automation_type)
            rec.scenarios_json = projections
            rec.estimated_roi = Decimal(str(projections["npv"]["expected"]))
            updated += 1
            logger.info(
                "recalculated rec=%s title=%s type=%s npv=%s",
                rec.id, rec.title[:40] if rec.title else "?",
                rec.automation_type, projections["npv"]["expected"],
            )
        except Exception as exc:
            errors += 1
            logger.exception("recalculate_failed rec=%s err=%s", rec.id, exc)
    await db.commit()
    logger.info("recalculate_all done updated=%d errors=%d total=%d", updated, errors, len(recs))
    return {"updated": updated, "errors": errors, "total": len(recs)}


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
