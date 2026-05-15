"""Full recommendation pipeline orchestration (async) — 4-phase agent opportunity engine."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataObject
from app.models.recommendation import Recommendation
from app.models.recommendation_run import RecommendationRun
from app.services.recommendations.arc_score import apply_arc_score
from app.services.recommendations.agent_analyzer import analyze_domain
from app.services.recommendations.cross_domain import synthesize_cross_domain
from app.services.recommendations.domain_assembler import assemble_domain_contexts
from app.services.recommendations.metadata_bindings import build_metadata_bindings
from app.workers.analysis import evaluate_agent_financials_task

logger = logging.getLogger(__name__)

_MAX_ERROR_LEN = 50_000


def _build_agent_recommendation(
    opp: dict,
    org_id: UUID,
    run_id: UUID,
    domain_id: UUID | None,
    rec_type: str = "agent_opportunity",
    *,
    process_contexts: list[dict] | None = None,
    salesforce_metadata: dict | None = None,
) -> Recommendation:
    opp = dict(opp or {})
    metadata_bindings = build_metadata_bindings(
        opp,
        process_contexts=process_contexts or [],
        salesforce_metadata=salesforce_metadata or {},
    )
    opp["metadata_binding_manifest_v1"] = metadata_bindings
    opp["metadata_bindings_v1"] = metadata_bindings
    opp["binding_model_version"] = metadata_bindings["binding_model_version"]

    title = (opp.get("agent_name") or "Untitled Agent Opportunity")[:512]

    topic_types = {t.get("reasoning_type", "hybrid") for t in opp.get("topics", [])}
    if topic_types == {"deterministic"}:
        auto_type = "deterministic"
    elif topic_types == {"agentic"}:
        auto_type = "agentic"
    else:
        auto_type = "hybrid"

    linked_proc_ids: list[str] = []
    linked_step_ids_list: list[str] = []
    for rep in opp.get("replaces", []):
        pid = rep.get("process_id")
        if pid:
            linked_proc_ids.append(str(pid))
        for sid in rep.get("step_ids", []):
            linked_step_ids_list.append(str(sid))

    rec = Recommendation(
        org_id=org_id,
        title=title,
        description=opp.get("description"),
        priority=None,
        category=opp.get("agent_type", "hybrid"),
        estimated_roi=None,
        composite_score=float(opp.get("confidence", 0.0)),
        status="active",
        analysis_inputs_json=[
            {
                "recommendation_type": rec_type,
                "complexity_estimate": opp.get("complexity_estimate"),
                "trigger": opp.get("trigger"),
            }
        ],
        actions_json=[
            {
                "step": i + 1,
                "action": f"{t.get('topic_name', 'Step')}: {t.get('description', '')}".strip(": "),
                "effort": {"deterministic": "low", "hybrid": "medium", "agentic": "high"}.get(
                    t.get("reasoning_type", ""), "medium"
                ),
            }
            for i, t in enumerate(opp.get("topics", []))
        ],
        impact_json={
            "data_requirements": opp.get("data_requirements", []),
            "integration_points": opp.get("integration_points", []),
            "risks": opp.get("risks", ""),
            "metadata_bindings_v1": metadata_bindings,
            "metadata_binding_manifest_v1": metadata_bindings,
            "binding_model_version": metadata_bindings["binding_model_version"],
        },
        architecture_health_json={},
        linked_process_ids=linked_proc_ids,
        recommendation_type=rec_type,
        automation_type=auto_type,
        base_score=None,
        llm_score=None,
        llm_rationale=opp.get("rationale"),
        score_divergence_flag=False,
        assumptions_json={},
        scenarios_json={},
        enrichment_log=[],
        agent_opportunity_json=opp,
        linked_step_ids=linked_step_ids_list,
        domain_id=domain_id,
        financial_evaluation_status="pending",
        recommendation_run_id=run_id,
    )
    apply_arc_score(rec)
    return rec


async def _load_salesforce_metadata_for_bindings(org_id: UUID, db: AsyncSession) -> dict:
    result = await db.execute(
        select(MetadataObject)
        .where(MetadataObject.org_id == org_id)
        .options(selectinload(MetadataObject.fields))
        .order_by(MetadataObject.api_name)
    )
    objects = list(result.scalars().unique().all())
    automation_result = await db.execute(
        select(MetadataAutomation)
        .where(MetadataAutomation.org_id == org_id)
        .order_by(MetadataAutomation.automation_type, MetadataAutomation.api_name)
    )
    automations = list(automation_result.scalars().all())
    component_result = await db.execute(
        select(MetadataComponent)
        .where(MetadataComponent.org_id == org_id)
        .order_by(MetadataComponent.component_category, MetadataComponent.api_name)
    )
    components = list(component_result.scalars().all())
    return {
        "objects": [
            {
                "api_name": obj.api_name,
                "label": obj.label,
                "fields": [
                    {
                        "api_name": field.api_name,
                        "label": field.label,
                        "field_type": field.field_type,
                    }
                    for field in (obj.fields or [])
                ],
            }
            for obj in objects
        ],
        "automations": [
            {
                "api_name": automation.api_name,
                "type": automation.automation_type,
                "label": automation.label,
                "related_object": automation.related_object,
                "status": automation.status,
            }
            for automation in automations
        ],
        "components": [
            {
                "api_name": component.api_name,
                "category": component.component_category,
                "label": component.label,
                "related_object": component.related_object,
                "status": component.status,
            }
            for component in components
        ],
    }


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

    async def _update_run_progress(
        stage_results: dict, current_stage: str | None = None
    ) -> None:
        """Flush stage_results + heartbeat and check for cancellation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        values: dict = {"stage_results": stage_results}
        cfg: dict = {"heartbeat_at": now_iso}
        if current_stage:
            cfg["current_stage"] = current_stage
        values["config"] = cfg
        await db.execute(
            update(RecommendationRun)
            .where(RecommendationRun.id == run_id)
            .values(**values)
        )
        await db.commit()
        await _check_cancelled()

    async def _heartbeat() -> None:
        """Update the run's heartbeat timestamp (called after each LLM batch)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.execute(
            update(RecommendationRun)
            .where(RecommendationRun.id == run_id)
            .values(
                config={"current_stage": "phase_2", "heartbeat_at": now_iso}
            )
        )
        await db.commit()

    try:
        stage_results: dict = {}

        # --- Phase 1: Domain context assembly ---
        logger.info("pipeline_stage org=%s run=%s phase=1_domain_context", org_id, run_id)
        await _update_run_progress(stage_results, "phase_1")
        t0 = time.perf_counter()
        domain_contexts = await assemble_domain_contexts(org_id, db)
        stage_results["phase_1"] = {
            "domains_count": len(domain_contexts),
            "seconds": round(time.perf_counter() - t0, 4),
        }
        pipeline_discovery_run_id: UUID | None = None
        if domain_contexts:
            raw_dr = domain_contexts[0].get("_discovery_run_id")
            if raw_dr is not None:
                pipeline_discovery_run_id = (
                    raw_dr if isinstance(raw_dr, UUID) else UUID(str(raw_dr))
                )
        logger.info(
            "pipeline_stage_done org=%s run=%s phase=1 domains=%d elapsed=%.1fs",
            org_id,
            run_id,
            len(domain_contexts),
            time.perf_counter() - t0,
        )
        await _update_run_progress(stage_results, "phase_2")

        # --- Phase 2: Per-domain agent opportunity analysis ---
        all_domain_results: list[dict] = []
        t0 = time.perf_counter()
        for domain_ctx in domain_contexts:
            result = await analyze_domain(
                domain_ctx,
                org_id,
                db,
                cancel_check=_check_cancelled,
                heartbeat=_heartbeat,
            )
            result["_domain_name"] = domain_ctx["domain"]["name"]
            result["_domain_db_id"] = domain_ctx.get("_domain_db_id")
            result["_discovery_run_id"] = domain_ctx.get("_discovery_run_id")
            result["_processes_raw"] = domain_ctx.get("processes", [])
            all_domain_results.append(result)
        total_opportunities = sum(
            len(r.get("agent_opportunities", [])) for r in all_domain_results
        )
        stage_results["phase_2"] = {
            "total_opportunities": total_opportunities,
            "domains_analyzed": len(all_domain_results),
            "seconds": round(time.perf_counter() - t0, 4),
        }
        logger.info(
            "pipeline_stage_done org=%s run=%s phase=2 opps=%d domains=%d elapsed=%.1fs",
            org_id,
            run_id,
            total_opportunities,
            len(all_domain_results),
            time.perf_counter() - t0,
        )
        await _update_run_progress(stage_results, "phase_3")

        # --- Phase 3: Cross-domain synthesis ---
        cross_result: dict | None = None
        if len(all_domain_results) >= 2 and pipeline_discovery_run_id is not None:
            t0 = time.perf_counter()
            cross_result = await synthesize_cross_domain(
                all_domain_results, org_id, pipeline_discovery_run_id, db
            )
            c_opps = cross_result.get("cross_domain_opportunities") or []
            c_merge = cross_result.get("merge_suggestions") or []
            stage_results["phase_3"] = {
                "seconds": round(time.perf_counter() - t0, 4),
                "cross_domain_opportunities": len(c_opps),
                "merge_suggestions": len(c_merge),
            }
            logger.info(
                "pipeline_stage_done org=%s run=%s phase=3 cross=%d merge_sug=%d elapsed=%.1fs",
                org_id,
                run_id,
                len(c_opps),
                len(c_merge),
                time.perf_counter() - t0,
            )
        else:
            stage_results["phase_3"] = {
                "skipped": True,
                "reason": "need_two_plus_domains_with_discovery",
            }
        await _update_run_progress(stage_results, "phase_4_persist")

        # --- Phase 4: Persist recommendations, enqueue financial evaluation ---
        salesforce_metadata = await _load_salesforce_metadata_for_bindings(org_id, db)
        all_process_contexts = [
            proc
            for domain_result in all_domain_results
            for proc in domain_result.get("_processes_raw", [])
            if isinstance(proc, dict)
        ]
        await db.execute(
            delete(Recommendation).where(
                Recommendation.org_id == org_id,
                Recommendation.recommendation_run_id.is_not(None),
                Recommendation.status.not_in(["accepted", "dismissed", "implemented"]),
            )
        )
        await db.commit()

        created_count = 0
        for r in all_domain_results:
            raw_did = r.get("_domain_db_id")
            domain_id: UUID | None
            if raw_did is not None:
                domain_id = raw_did if isinstance(raw_did, UUID) else UUID(str(raw_did))
            else:
                domain_id = None
            for opp in r.get("agent_opportunities", []):
                rec = _build_agent_recommendation(
                    opp,
                    org_id,
                    run_id,
                    domain_id,
                    rec_type="agent_opportunity",
                    process_contexts=r.get("_processes_raw", []),
                    salesforce_metadata=salesforce_metadata,
                )
                db.add(rec)
                created_count += 1
                if created_count % 5 == 0:
                    await db.commit()

        if cross_result is not None:
            for opp in cross_result.get("cross_domain_opportunities") or []:
                rec = _build_agent_recommendation(
                    opp,
                    org_id,
                    run_id,
                    None,
                    rec_type="agent_opportunity",
                    process_contexts=all_process_contexts,
                    salesforce_metadata=salesforce_metadata,
                )
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
                config={
                    "discovery_run_id": str(pipeline_discovery_run_id)
                    if pipeline_discovery_run_id
                    else None,
                    "model": "anthropic/claude-sonnet-4-6",
                    "pipeline": "agent_opportunity_4phase",
                    "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        await db.commit()

        evaluate_agent_financials_task.delay(str(org_id), str(run_id))

        logger.info(
            "pipeline_completed org=%s run=%s recommendations=%d",
            org_id,
            run_id,
            created_count,
        )
        return run_id

    except PipelineCancelled:
        logger.info(
            "recommendation_pipeline_cancelled org_id=%s run_id=%s", org_id, run_id
        )
        await db.rollback()
        await db.execute(
            update(RecommendationRun)
            .where(RecommendationRun.id == run_id)
            .values(completed_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return run_id

    except Exception as e:
        logger.exception(
            "recommendation_pipeline_failed org_id=%s run_id=%s", org_id, run_id
        )
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
