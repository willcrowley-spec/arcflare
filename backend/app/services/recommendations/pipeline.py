"""Full recommendation pipeline orchestration (async) — 4-phase agent opportunity engine."""
from __future__ import annotations

import asyncio
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
from app.core.config import get_settings
from app.services.ai.operations import resolve_model
from app.services.prompts.resolver import resolve_prompt_blocks
from app.services.recommendations.arc_score import apply_arc_score
from app.services.recommendations.agent_analyzer import analyze_domain
from app.services.recommendations.cross_domain import synthesize_cross_domain
from app.services.recommendations.domain_assembler import assemble_domain_contexts
from app.services.recommendations.metadata_bindings import build_metadata_bindings
from app.services.recommendations.readiness import (
    build_recommendation_readiness,
    classify_opportunity,
)
from app.workers.analysis import evaluate_agent_financials_task

logger = logging.getLogger(__name__)

_MAX_ERROR_LEN = 50_000


def _portfolio_title(opportunity: dict, readiness: dict) -> str:
    title = str(
        opportunity.get("agent_name")
        or opportunity.get("candidate_name")
        or "Untitled Portfolio Candidate"
    ).strip()
    if readiness.get("recommended_build_path") != "agentforce_agent" and title.lower().endswith(" agent"):
        title = title[:-6].strip()
    return title or "Untitled Portfolio Candidate"


async def analyze_domain_contexts(
    domain_contexts: list[dict],
    *,
    org_id: UUID,
    db: AsyncSession,
    prompt_blocks: dict[str, str],
    concurrency: int,
    analyzer=analyze_domain,
    cancel_check=None,
    heartbeat=None,
) -> list[dict]:
    """Analyze domains with bounded parallelism.

    The analyzer itself offloads provider calls to worker threads. Database access
    for cancellation/heartbeat is guarded because the pipeline owns one session.
    """
    limit = max(1, int(concurrency or 1))
    semaphore = asyncio.Semaphore(limit)
    db_lock = asyncio.Lock()

    async def _locked_cancel_check() -> None:
        if cancel_check is None:
            return
        async with db_lock:
            await cancel_check()

    async def _locked_heartbeat() -> None:
        if heartbeat is None:
            return
        async with db_lock:
            await heartbeat()

    async def _run_one(domain_ctx: dict) -> dict:
        async with semaphore:
            result = await analyzer(
                domain_ctx,
                org_id,
                db,
                cancel_check=_locked_cancel_check if cancel_check else None,
                heartbeat=_locked_heartbeat if heartbeat else None,
                prompt_blocks=prompt_blocks,
            )
            result["_domain_name"] = domain_ctx["domain"]["name"]
            result["_domain_db_id"] = domain_ctx.get("_domain_db_id")
            result["_discovery_run_id"] = domain_ctx.get("_discovery_run_id")
            result["_processes_raw"] = domain_ctx.get("processes", [])
            return result

    return list(await asyncio.gather(*(_run_one(ctx) for ctx in domain_contexts)))


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
    opp = normalize_opportunity_replacements(opp, process_contexts or []) or opp
    metadata_bindings = build_metadata_bindings(
        opp,
        process_contexts=process_contexts or [],
        salesforce_metadata=salesforce_metadata or {},
    )
    opp["metadata_binding_manifest_v1"] = metadata_bindings
    opp["metadata_bindings_v1"] = metadata_bindings
    opp["binding_model_version"] = metadata_bindings["binding_model_version"]
    preliminary_readiness = classify_opportunity(opp)

    title = _portfolio_title(opp, preliminary_readiness)[:512]

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
        category=preliminary_readiness["candidate_type"],
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
    readiness = build_recommendation_readiness(rec)
    rec.category = readiness["candidate_type"]
    rec.impact_json = {
        **(rec.impact_json or {}),
        "recommendation_readiness": readiness,
    }
    rec.agent_opportunity_json = {
        **(rec.agent_opportunity_json or {}),
        "recommendation_readiness": readiness,
    }
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
                "object_type": obj.object_type,
                "metadata_json": obj.metadata_json,
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


def _normalize_name(value: object) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split()
    )


def _context_lookup(
    process_contexts: list[dict] | None,
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict], dict[str, list[dict]]]:
    process_by_id: dict[str, dict] = {}
    process_by_name: dict[str, dict] = {}
    step_by_id: dict[str, dict] = {}
    steps_by_process_id: dict[str, list[dict]] = {}

    for process in process_contexts or []:
        if not isinstance(process, dict):
            continue
        process_id = str(process.get("id") or "").strip()
        if not process_id:
            continue
        process_by_id[process_id] = process
        process_name = _normalize_name(process.get("name"))
        if process_name and process_name not in process_by_name:
            process_by_name[process_name] = process
        steps: list[dict] = []
        for step in process.get("steps") or []:
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("id") or "").strip()
            if not step_id:
                continue
            step_row = {**step, "_process_id": process_id}
            step_by_id[step_id] = step_row
            steps.append(step_row)
        steps_by_process_id[process_id] = steps
    return process_by_id, process_by_name, step_by_id, steps_by_process_id


def normalize_opportunity_replacements(
    opportunity: dict,
    process_contexts: list[dict] | None,
) -> dict | None:
    """Canonicalize replacement process/step ids against the evidence graph.

    LLMs sometimes invent readable ids such as ``lead_ingestion_web``. Those
    must not be persisted as if they were Arcflare process ids. When we can
    map by exact process/step name, we rewrite to the real ids; otherwise the
    opportunity is not evidence-backed enough to persist.
    """
    opp = dict(opportunity or {})
    replacements = [r for r in opp.get("replaces") or [] if isinstance(r, dict)]
    if not replacements:
        return None

    process_by_id, process_by_name, step_by_id, steps_by_process_id = _context_lookup(
        process_contexts
    )
    if not process_by_id:
        return opp

    normalized_replacements: list[dict] = []
    for replacement in replacements:
        raw_process_id = str(replacement.get("process_id") or "").strip()
        process = process_by_id.get(raw_process_id)
        if process is None:
            process = process_by_name.get(_normalize_name(replacement.get("process_name")))
        if process is None:
            continue

        process_id = str(process.get("id"))
        process_steps = steps_by_process_id.get(process_id) or []
        step_ids: list[str] = []
        for raw_step_id in replacement.get("step_ids") or []:
            step_id = str(raw_step_id or "").strip()
            step = step_by_id.get(step_id)
            if step and step.get("_process_id") == process_id and step_id not in step_ids:
                step_ids.append(step_id)

        step_name_index = {
            _normalize_name(step.get("name")): str(step.get("id"))
            for step in process_steps
            if step.get("id") and _normalize_name(step.get("name"))
        }
        for step_name in replacement.get("steps_replaced") or []:
            mapped_step_id = step_name_index.get(_normalize_name(step_name))
            if mapped_step_id and mapped_step_id not in step_ids:
                step_ids.append(mapped_step_id)

        if not step_ids:
            if process_steps and (
                not replacement.get("steps_replaced")
                or str(replacement.get("replacement_type") or "").lower() == "full"
            ):
                step_ids = [str(step["id"]) for step in process_steps if step.get("id")]
            elif not process_steps:
                step_ids = [process_id]

        normalized_replacements.append(
            {
                **replacement,
                "process_id": process_id,
                "process_name": process.get("name") or replacement.get("process_name"),
                "step_ids": step_ids,
            }
        )

    if not normalized_replacements:
        return None

    opp["replaces"] = normalized_replacements
    return opp


def _opportunity_signature(opp: dict) -> tuple:
    name = " ".join(str(opp.get("agent_name") or "").lower().split())
    processes: list[str] = []
    steps: list[str] = []
    for rep in opp.get("replaces") or []:
        if not isinstance(rep, dict):
            continue
        if rep.get("process_id"):
            processes.append(str(rep["process_id"]))
        steps.extend(str(sid) for sid in rep.get("step_ids") or [] if sid)
    topics = sorted(
        " ".join(str(t.get("topic_name") or "").lower().split())
        for t in (opp.get("topics") or [])
        if isinstance(t, dict)
    )
    return (
        name,
        tuple(sorted(set(processes))),
        tuple(sorted(set(steps))),
        tuple(topics),
    )


def _dedupe_opportunities(items: list[dict]) -> list[dict]:
    """Keep the strongest deterministic duplicate before persistence."""
    by_sig: dict[tuple, dict] = {}
    for item in items:
        opp = item.get("opportunity") or {}
        sig = _opportunity_signature(opp)
        if not sig[0]:
            continue
        existing = by_sig.get(sig)
        if existing is None:
            by_sig[sig] = item
            continue
        new_conf = float((opp or {}).get("confidence") or 0.0)
        old_conf = float(((existing.get("opportunity") or {}).get("confidence")) or 0.0)
        if new_conf > old_conf:
            by_sig[sig] = item
    return list(by_sig.values())


def _is_semantically_valid_opportunity(opp: dict) -> bool:
    if not isinstance(opp, dict):
        return False
    if not str(opp.get("agent_name") or "").strip():
        return False
    if not (opp.get("topics") or []):
        return False
    if not (opp.get("replaces") or []):
        return False
    confidence = opp.get("confidence", 0)
    try:
        confidence_float = float(confidence)
    except (TypeError, ValueError):
        return False
    return 0.0 <= confidence_float <= 1.0


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
        t0 = time.perf_counter()
        settings = get_settings()
        agent_prompt_blocks = await resolve_prompt_blocks("agent_opportunity", org_id, db)
        all_domain_results = await analyze_domain_contexts(
            domain_contexts,
            org_id=org_id,
            db=db,
            prompt_blocks=agent_prompt_blocks,
            concurrency=settings.RECOMMENDATION_DOMAIN_CONCURRENCY,
            cancel_check=_check_cancelled,
            heartbeat=_heartbeat,
        )
        total_opportunities = sum(
            len(r.get("agent_opportunities", [])) for r in all_domain_results
        )
        stage_results["phase_2"] = {
            "total_opportunities": total_opportunities,
            "domains_analyzed": len(all_domain_results),
            "domain_concurrency": settings.RECOMMENDATION_DOMAIN_CONCURRENCY,
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

        opportunity_items: list[dict] = []
        for r in all_domain_results:
            raw_did = r.get("_domain_db_id")
            domain_id: UUID | None
            if raw_did is not None:
                domain_id = raw_did if isinstance(raw_did, UUID) else UUID(str(raw_did))
            else:
                domain_id = None
            for opp in r.get("agent_opportunities", []):
                normalized_opp = normalize_opportunity_replacements(
                    opp, r.get("_processes_raw", [])
                )
                if normalized_opp is None or not _is_semantically_valid_opportunity(normalized_opp):
                    continue
                opportunity_items.append(
                    {
                        "opportunity": normalized_opp,
                        "domain_id": domain_id,
                        "rec_type": "agent_opportunity",
                        "process_contexts": r.get("_processes_raw", []),
                    }
                )

        if cross_result is not None:
            for opp in cross_result.get("cross_domain_opportunities") or []:
                normalized_opp = normalize_opportunity_replacements(opp, all_process_contexts)
                if normalized_opp is None or not _is_semantically_valid_opportunity(normalized_opp):
                    continue
                opportunity_items.append(
                    {
                        "opportunity": normalized_opp,
                        "domain_id": None,
                        "rec_type": "agent_opportunity",
                        "process_contexts": all_process_contexts,
                    }
                )

        deduped_items = _dedupe_opportunities(opportunity_items)
        created_count = 0
        for item in deduped_items:
            rec = _build_agent_recommendation(
                item["opportunity"],
                org_id,
                run_id,
                item["domain_id"],
                rec_type=item["rec_type"],
                process_contexts=item["process_contexts"],
                salesforce_metadata=salesforce_metadata,
            )
            db.add(rec)
            created_count += 1
            if created_count % 5 == 0:
                await db.commit()

        stage_results["summary"] = {
            "recommendations_created": created_count,
            "recommendations_before_dedupe": len(opportunity_items),
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
                    "model": resolve_model(operation="agent_opportunity", tier="strong"),
                    "domain_concurrency": get_settings().RECOMMENDATION_DOMAIN_CONCURRENCY,
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
