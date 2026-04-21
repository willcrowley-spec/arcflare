"""Full recommendation pipeline orchestration (async)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import ProcessHandoff
from app.models.recommendation import Recommendation
from app.models.recommendation_run import RecommendationRun
from app.services.recommendations.candidate_generator import (
    generate_discovered_candidates,
    generate_synthesized_candidates,
)
from app.services.recommendations.financial_engine import compute_projections
from app.services.recommendations.heuristic_scorer import score_process, score_synthesized
from app.services.recommendations.llm_scorer import score_candidates_with_llm

logger = logging.getLogger(__name__)

_MAX_ERROR_LEN = 50_000


def _norm_automation_type(value: object | None) -> str:
    s = (str(value).strip() if value is not None else "") or "hybrid"
    return s[:20]


def _linked_process_ids_for_rec(candidate: dict) -> list[UUID]:
    if candidate.get("recommendation_type") == "synthesized":
        raw = candidate.get("linked_process_ids") or []
        return [UUID(str(x)) for x in raw]
    pid = candidate.get("id")
    if pid is None:
        return []
    return [UUID(str(pid))]


async def _eliminated_gap_handoff_count(
    org_id: UUID,
    discovery_run_id: UUID,
    linked_ids: list[str],
    db: AsyncSession,
) -> int:
    if len(linked_ids) < 2:
        return 0
    id_set = set(linked_ids)
    res = await db.execute(
        select(ProcessHandoff.source_process_id, ProcessHandoff.target_process_id).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == discovery_run_id,
            ProcessHandoff.is_gap.is_(True),
        )
    )
    n = 0
    for src, tgt in res.all():
        if str(src) in id_set and str(tgt) in id_set:
            n += 1
    return n


def _build_recommendation(
    candidate: dict,
    org_id: UUID,
    recommendation_run_id: UUID,
    projections: dict,
) -> Recommendation:
    rec_type = candidate.get("recommendation_type") or "discovered"
    title = (
        (candidate.get("title") or candidate.get("name") or "").strip()
        or ("Synthesized opportunity" if rec_type == "synthesized" else "Untitled process")
    )
    description = candidate.get("description") or candidate.get("narrative")
    expected_npv = projections.get("expected", {}).get("npv")
    est_roi: float | None
    if expected_npv is None:
        est_roi = None
    else:
        est_roi = float(expected_npv)

    assumptions = candidate.get("assumptions_json")
    if not isinstance(assumptions, dict):
        assumptions = {}

    actions = candidate.get("actions_json")
    if not isinstance(actions, list):
        actions = []

    base_score = candidate.get("base_score")
    llm_score = candidate.get("llm_score")
    composite = candidate.get("composite_score")

    return Recommendation(
        org_id=org_id,
        title=title[:512],
        description=description,
        priority=None,
        category=(candidate.get("category") if rec_type == "discovered" else "composite"),
        estimated_roi=Decimal(str(round(est_roi, 2))) if est_roi is not None else None,
        composite_score=float(composite) if composite is not None else None,
        status="active",
        analysis_inputs_json=[
            {
                "recommendation_type": rec_type,
                "signals": candidate.get("signals"),
                "gate_score": candidate.get("gate_score"),
                "refinement_score": candidate.get("refinement_score"),
            }
        ],
        actions_json=actions,
        impact_json=dict(candidate.get("signals") or {}),
        architecture_health_json={},
        linked_process_ids=_linked_process_ids_for_rec(candidate),
        recommendation_type=rec_type if rec_type in ("discovered", "synthesized") else "discovered",
        automation_type=_norm_automation_type(candidate.get("automation_type")),
        base_score=float(base_score) if base_score is not None else None,
        llm_score=float(llm_score) if llm_score is not None else None,
        llm_rationale=candidate.get("llm_rationale"),
        score_divergence_flag=bool(candidate.get("score_divergence_flag")),
        assumptions_json=assumptions,
        scenarios_json=projections,
        enrichment_log=[],
        recommendation_run_id=recommendation_run_id,
    )


async def run_recommendation_pipeline(
    org_id: UUID,
    db: AsyncSession,
    existing_run_id: UUID | None = None,
) -> UUID:
    """Run the full recommendation pipeline. Returns the RecommendationRun ID.

    If *existing_run_id* is provided (pre-created by the API route for
    immediate polling), that row is reused.  Otherwise a new run is created.
    """
    if existing_run_id is not None:
        run = await db.get(RecommendationRun, existing_run_id)
        if run is None:
            run = RecommendationRun(org_id=org_id, status="running", config={})
            db.add(run)
        else:
            run.status = "running"
        await db.commit()
        await db.refresh(run)
    else:
        run = RecommendationRun(org_id=org_id, status="running", config={})
        db.add(run)
        await db.commit()
        await db.refresh(run)
    run_id = run.id

    class PipelineCancelled(Exception):
        pass

    async def _check_cancelled() -> None:
        """Re-read the run row; raise if someone set status='cancelled'."""
        row = await db.execute(
            select(RecommendationRun.status).where(RecommendationRun.id == run_id)
        )
        current = row.scalar_one_or_none()
        if current == "cancelled":
            raise PipelineCancelled()

    async def _update_run_progress(stage_results: dict, current_stage: str | None = None) -> None:
        """Flush stage_results and check for cancellation."""
        values: dict = {"stage_results": stage_results}
        if current_stage:
            values["config"] = {"current_stage": current_stage}
        await db.execute(
            update(RecommendationRun).where(RecommendationRun.id == run_id).values(**values)
        )
        await db.commit()
        await _check_cancelled()

    try:
        stage_results: dict = {}

        # --- Stage 1: Candidate generation ---
        logger.info("pipeline_stage org=%s run=%s stage=1_candidates", org_id, run_id)
        await _update_run_progress(stage_results, "stage_1_candidates")
        t0 = time.perf_counter()
        discovered = await generate_discovered_candidates(org_id, db)
        synthesized = await generate_synthesized_candidates(org_id, discovered, db)
        stage_results["stage_1"] = {
            "seconds": round(time.perf_counter() - t0, 4),
            "discovered_count": len(discovered),
            "synthesized_count": len(synthesized),
        }
        logger.info(
            "pipeline_stage_done org=%s run=%s stage=1 discovered=%d synthesized=%d elapsed=%.1fs",
            org_id, run_id, len(discovered), len(synthesized), time.perf_counter() - t0,
        )
        await _update_run_progress(stage_results, "stage_2_scoring")

        # --- Stage 2: Heuristic scoring ---
        t0 = time.perf_counter()
        discovered_by_id: dict[str, dict] = {str(d["id"]): d for d in discovered}
        all_candidates: list[dict] = []

        for row in discovered:
            scored = score_process(row)
            merged = {**row, **scored}
            all_candidates.append(merged)

        for synth in synthesized:
            linked = synth.get("linked_process_ids") or []
            constituents = [discovered_by_id[lp] for lp in linked if lp in discovered_by_id]
            dr_id = synth.get("discovery_run_id")
            handoff_n = 0
            if dr_id is not None:
                handoff_n = await _eliminated_gap_handoff_count(org_id, dr_id, linked, db)
            scored = score_synthesized(constituents, handoff_n)
            merged = {**synth, **scored}
            all_candidates.append(merged)

        stage_results["stage_2"] = {
            "seconds": round(time.perf_counter() - t0, 4),
            "candidates_scored": len(all_candidates),
        }
        logger.info(
            "pipeline_stage_done org=%s run=%s stage=2 scored=%d elapsed=%.1fs",
            org_id, run_id, len(all_candidates), time.perf_counter() - t0,
        )
        await _update_run_progress(stage_results, "stage_3_llm")

        # --- Stage 3: LLM scoring + narrative ---
        logger.info("pipeline_stage org=%s run=%s stage=3_llm candidates=%d", org_id, run_id, len(all_candidates))
        t0 = time.perf_counter()
        llm_out = await score_candidates_with_llm(all_candidates, cancel_check=_check_cancelled)
        stage_results["stage_3"] = {
            "seconds": round(time.perf_counter() - t0, 4),
            "llm_candidates": len(llm_out),
        }
        logger.info(
            "pipeline_stage_done org=%s run=%s stage=3 llm_scored=%d elapsed=%.1fs",
            org_id, run_id, len(llm_out), time.perf_counter() - t0,
        )
        await _update_run_progress(stage_results, "stage_4_persist")

        # --- Stage 4: Composite scoring + financial projections + persist ---
        logger.info("pipeline_stage org=%s run=%s stage=4_persist count=%d", org_id, run_id, len(llm_out))
        for c in llm_out:
            base = float(c.get("base_score") or 0.0)
            llm = c.get("llm_score")
            llm_part = float(llm) if llm is not None else base
            c["composite_score"] = round(base * 0.7 + llm_part * 0.3, 6)
            c["score_divergence_flag"] = llm is not None and abs(base - float(llm)) > 0.25

        await db.execute(
            delete(Recommendation).where(
                Recommendation.org_id == org_id,
                Recommendation.recommendation_run_id.is_not(None),
                Recommendation.status != "accepted",
            )
        )
        await db.commit()

        created_count = 0
        for c in llm_out:
            assumptions = c.get("assumptions_json")
            if not isinstance(assumptions, dict):
                assumptions = {}
            projections = compute_projections(assumptions)
            rec = _build_recommendation(c, org_id, run_id, projections)
            db.add(rec)
            created_count += 1
            if created_count % 5 == 0:
                await db.commit()

        stage_results["summary"] = {
            "recommendations_created": created_count,
        }

        await db.execute(
            update(RecommendationRun)
            .where(RecommendationRun.id == run_id)
            .values(
                status="completed",
                completed_at=datetime.now(timezone.utc),
                stage_results=stage_results,
                error=None,
                config={},
            )
        )
        await db.commit()
        logger.info(
            "pipeline_completed org=%s run=%s recommendations=%d",
            org_id, run_id, created_count,
        )
        return run_id

    except PipelineCancelled:
        logger.info("recommendation_pipeline_cancelled org_id=%s run_id=%s", org_id, run_id)
        await db.rollback()
        await db.execute(
            update(RecommendationRun)
            .where(RecommendationRun.id == run_id)
            .values(completed_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return run_id

    except Exception as e:
        logger.exception("recommendation_pipeline_failed org_id=%s run_id=%s", org_id, run_id)
        await db.rollback()
        err_text = str(e)[:_MAX_ERROR_LEN]
        await db.execute(
            update(RecommendationRun)
            .where(RecommendationRun.id == run_id)
            .values(
                status="failed",
                error=err_text,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        raise
