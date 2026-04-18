"""Seven-stage process discovery intelligence pipeline."""
from __future__ import annotations

import logging
import statistics
import time
from typing import Callable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import langfuse_score, langfuse_span as _lf_span
from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.metadata import MetadataAutomation, MetadataObject
from app.models.process import BusinessProcess, ProcessEdge, ProcessNode
from app.services.ai.router import LLMResult, llm_call, parse_json_response
from app.services.processes.context import (
    gather_metadata_for_domain,
    gather_metadata_relationships,
    gather_metadata_summary,
    gather_org_context,
    semantic_document_search,
)
from app.services.processes.prompts import (
    build_pass1_prompt,
    build_pass3_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    build_stage4_prompt,
    build_stage5_prompt,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int, int], None] | None

NEEDS_REVIEW_CONFIDENCE = 0.6


def _empty_llm_result() -> LLMResult:
    return LLMResult(text="{}", input_tokens=0, output_tokens=0, model="", provider="")


def _safe_parse(text: str, label: str) -> dict:
    """Parse JSON from LLM response; return empty dict on failure."""
    try:
        result = parse_json_response(text)
        if isinstance(result, dict):
            return result
        logger.warning("parse_non_dict label=%s type=%s", label, type(result).__name__)
        return {"items": result}
    except Exception as exc:
        logger.error(
            "json_parse_failed label=%s error=%s text_start=%s",
            label,
            exc,
            (text or "")[:200],
        )
        return {}


def _call_with_retry(
    prompt: str,
    max_tokens: int,
    tier: str,
    operation: str,
    label: str,
    model_config: dict | None = None,
    retries: int = 1,
    budget_multiplier: float = 1.5,
) -> tuple[LLMResult, dict]:
    """LLM call with automatic retry on JSON parse failure.

    Returns (result, parsed_dict).  On the retry attempt, ``max_tokens``
    is multiplied by ``budget_multiplier`` to give the model more room.
    """
    for attempt in range(1 + retries):
        tokens = int(max_tokens * (budget_multiplier ** attempt))
        try:
            result = llm_call(
                prompt=prompt, max_tokens=tokens, tier=tier,
                operation=operation, model_config=model_config,
            )
        except Exception as exc:
            logger.error(
                "llm_call_failed label=%s attempt=%d error=%s",
                label, attempt + 1, exc,
            )
            if attempt < retries:
                continue
            return _empty_llm_result(), {}

        parsed = _safe_parse(result.text, label)
        if parsed:
            return result, parsed

        if attempt < retries:
            logger.warning(
                "retry_json_parse label=%s attempt=%d next_tokens=%d",
                label, attempt + 1, int(tokens * budget_multiplier),
            )

    return result, parsed


def _as_list(val: object) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [val]
    return []


async def run_stage1(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> list[dict]:
    """Stage 1: Domain Discovery. Returns list of domain dicts."""
    start = time.time()

    with _lf_span("stage1_domain_discovery", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("domain_discovery", "gathering", 0, 1)

        org_ctx = await gather_org_context(org_id, db)
        meta_summary = await gather_metadata_summary(org_id, db)
        org_desc = org_ctx.get("description") or org_ctx.get("name", "")
        doc_chunks = await semantic_document_search(org_id, db, org_desc, limit=20)

        prompt = await build_pass1_prompt(
            org_id, db, org_ctx, meta_summary, doc_chunks,
        )

        result, parsed = _call_with_retry(
            prompt=prompt, max_tokens=8000, tier="strong",
            operation="discovery_domain", label="stage1",
            model_config=model_config,
        )

        raw_domains = parsed.get("domains") or parsed.get("items")
        if isinstance(raw_domains, list):
            domains = raw_domains
        else:
            if raw_domains is not None:
                logger.warning(
                    "stage1_domains_wrong_type org_id=%s type=%s",
                    org_id,
                    type(raw_domains).__name__,
                )
            domains = []

        logger.info(
            "stage1_complete org_id=%s run_id=%s domains=%d tokens_in=%d tokens_out=%d dur_ms=%d",
            org_id,
            run_id,
            len(domains),
            result.input_tokens,
            result.output_tokens,
            int((time.time() - start) * 1000),
        )

        for domain in domains:
            if not isinstance(domain, dict):
                continue
            confidence = float(domain.get("confidence", 0.5))
            proc = BusinessProcess(
                org_id=org_id,
                name=str(domain.get("name", "Unnamed Domain"))[:255],
                description=domain.get("description"),
                level="domain",
                parent_id=None,
                confidence_score=confidence,
                needs_review=confidence < NEEDS_REVIEW_CONFIDENCE,
                narrative=domain.get("reasoning"),
                status="discovered",
                source="discovery",
                discovery_run_id=run_id,
                actors=_as_list(domain.get("actors")),
                artifacts=_as_list(domain.get("artifacts")),
                metadata_json={
                    "associated_objects": _as_list(domain.get("associated_objects")),
                    "associated_automations": _as_list(domain.get("associated_automations")),
                    "associated_documents": _as_list(domain.get("associated_documents")),
                },
            )
            db.add(proc)

        await db.flush()

        if progress_cb:
            progress_cb("domain_discovery", "done", 1, 1)

        return domains


async def run_stage2(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Stage 2: Structural decomposition per domain. Returns total process rows created."""
    start = time.time()
    total_input_tokens = 0
    total_output_tokens = 0

    with _lf_span("stage2_structural_decomposition", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        org_ctx = await gather_org_context(org_id, db)

        domains_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.level == "domain",
                BusinessProcess.status != "rejected",
            )
        )
        domains = domains_q.scalars().all()
        total_processes = 0

        for i, domain in enumerate(domains):
            if progress_cb:
                progress_cb("structural_decomposition", "running", i, len(domains))

            meta_json = domain.metadata_json or {}
            object_names = _as_list(meta_json.get("associated_objects"))
            automation_names = _as_list(meta_json.get("associated_automations"))
            str_objects = [str(x) for x in object_names if x]
            str_automations = [str(x) for x in automation_names if x]

            meta_detail = await gather_metadata_for_domain(
                org_id, db, str_objects, str_automations
            )
            doc_chunks = await semantic_document_search(
                org_id, db, f"{domain.name}: {domain.description or ''}", limit=20
            )

            domain_dict = {"name": domain.name, "description": domain.description or ""}
            prompt = await build_stage2_prompt(
                org_id, db, org_ctx, domain_dict, meta_detail, doc_chunks,
            )

            with _lf_span(
                f"stage2_domain_{domain.name}",
                metadata={"domain_index": i, "domain_total": len(domains)},
            ):
                result, parsed = _call_with_retry(
                    prompt=prompt, max_tokens=8000, tier="strong",
                    operation="discovery_structure",
                    label=f"stage2_domain_{domain.name}",
                    model_config=model_config,
                )
                total_input_tokens += result.input_tokens
                total_output_tokens += result.output_tokens

            raw_procs = parsed.get("processes") or parsed.get("items")
            if isinstance(raw_procs, list):
                processes = raw_procs
            else:
                if raw_procs is not None:
                    logger.warning(
                        "stage2_processes_wrong_type domain=%s type=%s",
                        domain.name,
                        type(raw_procs).__name__,
                    )
                processes = []

            async def persist_process(proc_data: dict, parent_id: UUID | None) -> None:
                nonlocal total_processes
                confidence = float(proc_data.get("confidence", 0.5))
                bp = BusinessProcess(
                    org_id=org_id,
                    name=str(proc_data.get("name", "Unnamed"))[:255],
                    description=proc_data.get("description"),
                    level=str(proc_data.get("level", "process"))[:50],
                    parent_id=parent_id,
                    confidence_score=confidence,
                    needs_review=bool(proc_data.get("needs_review", False))
                    or confidence < NEEDS_REVIEW_CONFIDENCE,
                    narrative=proc_data.get("narrative"),
                    status="discovered",
                    source="discovery",
                    discovery_run_id=run_id,
                    actors=_as_list(proc_data.get("actors")),
                    artifacts=_as_list(proc_data.get("artifacts")),
                    metadata_json={},
                )
                db.add(bp)
                await db.flush()
                total_processes += 1

                children = proc_data.get("children")
                if not isinstance(children, list):
                    children = []
                for child in children:
                    if isinstance(child, dict):
                        await persist_process(child, bp.id)

            for proc in processes:
                if isinstance(proc, dict):
                    await persist_process(proc, domain.id)

            domain.sub_process_count = len(processes)
            await db.flush()

        logger.info(
            "stage2_complete org_id=%s run_id=%s processes=%d domains=%d tokens_in=%d tokens_out=%d dur_ms=%d",
            org_id,
            run_id,
            total_processes,
            len(domains),
            total_input_tokens,
            total_output_tokens,
            int((time.time() - start) * 1000),
        )

        if progress_cb:
            progress_cb("structural_decomposition", "done", len(domains), len(domains))

        return total_processes


async def run_stage3(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Stage 3: Step Enrichment. Returns count of enriched steps."""
    start = time.time()
    enriched_count = 0

    with _lf_span("stage3_step_enrichment", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("step_enrichment", "running", 0, 1)

        domains_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.level == "domain",
                BusinessProcess.status != "rejected",
            )
        )
        domains = domains_q.scalars().all()

        for domain in domains:
            all_procs_q = await db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.status != "rejected",
                )
            )
            all_procs = all_procs_q.scalars().all()

            id_to_proc = {p.id: p for p in all_procs}
            domain_steps = []
            for p in all_procs:
                if p.level != "step":
                    continue
                current = p
                under_domain = False
                while current:
                    if current.id == domain.id:
                        under_domain = True
                        break
                    current = id_to_proc.get(current.parent_id)
                if under_domain:
                    domain_steps.append(p)

            if not domain_steps:
                continue

            steps_data = []
            metadata_per_step: dict[str, dict] = {}
            docs_per_step: dict[str, list[dict]] = {}

            for step in domain_steps:
                step_artifacts = step.artifacts or []
                obj_names = [a.get("api_name", "") for a in step_artifacts if a.get("type") == "object"]
                auto_names = [
                    a.get("api_name", "")
                    for a in step_artifacts
                    if a.get("type") in ("flow", "validation_rule")
                ]

                meta = await gather_metadata_for_domain(org_id, db, obj_names, auto_names)
                metadata_per_step[step.name] = meta

                docs = await semantic_document_search(
                    org_id, db, f"{step.name}: {step.description or ''}", limit=5
                )
                docs_per_step[step.name] = docs

                steps_data.append({
                    "name": step.name,
                    "description": step.description,
                    "artifacts": step_artifacts,
                })

            prompt = await build_stage3_prompt(
                org_id, db, steps_data, metadata_per_step, docs_per_step,
            )

            with _lf_span(f"stage3_domain_{domain.name}"):
                _result, parsed = _call_with_retry(
                    prompt=prompt, max_tokens=12000, tier="strong",
                    operation="discovery_enrichment",
                    label=f"stage3_{domain.name}",
                    model_config=model_config,
                )

            enriched_steps = _as_list(parsed.get("enriched_steps") or parsed.get("items"))
            name_to_step = {s.name: s for s in domain_steps}

            for es in enriched_steps:
                if not isinstance(es, dict):
                    continue
                step_name = str(es.get("name", ""))
                bp = name_to_step.get(step_name)
                if not bp:
                    continue

                bp.trigger_conditions = _as_list(es.get("trigger_conditions"))
                bp.decision_logic = _as_list(es.get("decision_logic"))
                bp.system_touchpoints = _as_list(es.get("system_touchpoints"))
                bp.actors = _as_list(es.get("actors"))
                bp.success_criteria = _as_list(es.get("success_criteria"))
                bp.failure_modes = _as_list(es.get("failure_modes"))
                bp.value_classification = es.get("value_classification")
                bp.complexity_score = es.get("complexity_score")
                bp.automation_potential = es.get("automation_potential")
                bp.estimated_duration = es.get("estimated_duration")
                bp.estimated_frequency = es.get("estimated_frequency")

                if es.get("confidence") is not None:
                    bp.confidence_score = float(es["confidence"])
                if es.get("needs_review") is not None:
                    bp.needs_review = bool(es["needs_review"])

                enriched_count += 1

            await db.flush()

        if progress_cb:
            progress_cb("step_enrichment", "done", enriched_count, max(enriched_count, 1))

        logger.info(
            "stage3_complete org_id=%s run_id=%s enriched=%d dur_ms=%d",
            org_id, run_id, enriched_count, int((time.time() - start) * 1000),
        )
        return enriched_count


async def run_stage4(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Stage 4: Flow & Handoff Analysis. Returns handoff count."""
    start = time.time()
    total_handoffs = 0

    with _lf_span("stage4_flow_analysis", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("flow_analysis", "running", 0, 1)

        domains_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.level == "domain",
                BusinessProcess.status != "rejected",
            )
        )
        domains = domains_q.scalars().all()

        for domain in domains:
            all_procs_q = await db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.status != "rejected",
                )
            )
            all_procs = all_procs_q.scalars().all()
            id_to_proc = {p.id: p for p in all_procs}

            domain_procs = []
            for p in all_procs:
                current = p
                under_domain = False
                while current:
                    if current.id == domain.id:
                        under_domain = True
                        break
                    current = id_to_proc.get(current.parent_id)
                if under_domain:
                    domain_procs.append(p)

            if not domain_procs:
                continue

            def build_tree_dict(proc: BusinessProcess) -> dict:
                return {
                    "name": proc.name,
                    "level": proc.level,
                    "description": proc.description,
                    "system_touchpoints": proc.system_touchpoints or [],
                    "trigger_conditions": proc.trigger_conditions or [],
                    "actors": proc.actors or [],
                    "children": [
                        build_tree_dict(c) for c in domain_procs if c.parent_id == proc.id
                    ],
                }

            enriched_tree = [
                build_tree_dict(p) for p in domain_procs if p.parent_id == domain.id
            ]

            all_objects: set[str] = set()
            for p in domain_procs:
                for tp in (p.system_touchpoints or []):
                    if isinstance(tp, dict) and tp.get("object_api_name"):
                        all_objects.add(tp["object_api_name"])
                for art in (p.artifacts or []):
                    if isinstance(art, dict) and art.get("type") == "object":
                        all_objects.add(art.get("api_name", ""))

            relationships = await gather_metadata_relationships(org_id, db, list(all_objects))

            prompt = await build_stage4_prompt(org_id, db, enriched_tree, relationships)

            with _lf_span(f"stage4_domain_{domain.name}"):
                _result, parsed = _call_with_retry(
                    prompt=prompt, max_tokens=10000, tier="strong",
                    operation="discovery_flow",
                    label=f"stage4_{domain.name}",
                    model_config=model_config,
                )

            name_to_id: dict[str, UUID] = {p.name: p.id for p in domain_procs}
            name_to_proc: dict[str, BusinessProcess] = {p.name: p for p in domain_procs}

            step_flows = _as_list(parsed.get("step_flows") or parsed.get("items"))
            ep_raw = parsed.get("entry_points")
            entry_points = set(ep_raw) if isinstance(ep_raw, list) else set()
            tp_raw = parsed.get("terminal_points")
            terminal_points = set(tp_raw) if isinstance(tp_raw, list) else set()
            parallel_groups = {
                step_name: pg.get("group_name", "")
                for pg in _as_list(parsed.get("parallel_groups"))
                if isinstance(pg, dict)
                for step_name in _as_list(pg.get("step_names"))
            }

            sequencing_map: dict[str, dict] = {}
            for p in domain_procs:
                if p.level == "step":
                    sequencing_map[p.name] = {
                        "predecessors": [],
                        "successors": [],
                        "parallel_group": parallel_groups.get(p.name),
                        "is_entry_point": p.name in entry_points,
                        "is_terminal": p.name in terminal_points,
                    }

            for sf in step_flows:
                if not isinstance(sf, dict):
                    continue
                src = str(sf.get("source_step", ""))
                tgt = str(sf.get("target_step", ""))
                condition = sf.get("condition")
                src_id = name_to_id.get(src)
                tgt_id = name_to_id.get(tgt)

                if src in sequencing_map and tgt_id:
                    sequencing_map[src]["successors"].append(
                        {"step_id": str(tgt_id), "condition": condition}
                    )
                if tgt in sequencing_map and src_id:
                    sequencing_map[tgt]["predecessors"].append(
                        {"step_id": str(src_id), "condition": condition}
                    )

            for step_name, seq in sequencing_map.items():
                bp = name_to_proc.get(step_name)
                if bp:
                    bp.sequencing = seq

            process_name_to_id: dict[str, UUID] = {}
            for p in domain_procs:
                if p.level in ("process", "subprocess"):
                    process_name_to_id[p.name] = p.id

            for ho in _as_list(parsed.get("handoffs")):
                if not isinstance(ho, dict):
                    continue
                src_id = process_name_to_id.get(str(ho.get("source", "")))
                tgt_id = process_name_to_id.get(str(ho.get("target", "")))
                if src_id and tgt_id:
                    confidence = float(ho.get("confidence", 0.5))
                    db.add(ProcessHandoff(
                        org_id=org_id,
                        source_process_id=src_id,
                        target_process_id=tgt_id,
                        handoff_type=str(ho.get("type", "unknown"))[:50],
                        description=ho.get("description"),
                        confidence_score=confidence,
                        is_gap=False,
                        needs_review=confidence < NEEDS_REVIEW_CONFIDENCE,
                        discovery_run_id=run_id,
                        metadata_json={
                            "data_transferred": _as_list(ho.get("data_transferred")),
                            "transfer_mechanism": ho.get("transfer_mechanism"),
                            "source_process": ho.get("source"),
                            "target_process": ho.get("target"),
                        },
                    ))
                    total_handoffs += 1

            await db.flush()

        if progress_cb:
            progress_cb("flow_analysis", "done", total_handoffs, max(total_handoffs, 1))

        logger.info(
            "stage4_complete org_id=%s run_id=%s handoffs=%d dur_ms=%d",
            org_id, run_id, total_handoffs, int((time.time() - start) * 1000),
        )
        return total_handoffs


async def run_stage5(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> dict:
    """Stage 5: Validation & Refinement. Returns combined critique."""
    start = time.time()
    all_critiques: list[dict] = []

    with _lf_span("stage5_validation", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("validation", "running", 0, 1)

        domains_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.level == "domain",
                BusinessProcess.status != "rejected",
            )
        )
        domains = domains_q.scalars().all()

        for domain in domains:
            all_procs_q = await db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.status != "rejected",
                )
            )
            all_procs = all_procs_q.scalars().all()
            id_to_proc = {p.id: p for p in all_procs}

            domain_procs = []
            for p in all_procs:
                current = p
                under_domain = False
                while current:
                    if current.id == domain.id:
                        under_domain = True
                        break
                    current = id_to_proc.get(current.parent_id)
                if under_domain:
                    domain_procs.append(p)

            if not domain_procs:
                continue

            def build_complete_tree(proc: BusinessProcess) -> dict:
                return {
                    "name": proc.name,
                    "level": proc.level,
                    "description": proc.description,
                    "confidence": proc.confidence_score,
                    "system_touchpoints": proc.system_touchpoints or [],
                    "trigger_conditions": proc.trigger_conditions or [],
                    "actors": proc.actors or [],
                    "artifacts": proc.artifacts or [],
                    "sequencing": proc.sequencing or {},
                    "value_classification": proc.value_classification,
                    "children": [
                        build_complete_tree(c)
                        for c in domain_procs if c.parent_id == proc.id
                    ],
                }

            complete_tree = [
                build_complete_tree(p) for p in domain_procs if p.parent_id == domain.id
            ]

            handoffs_q = await db.execute(
                select(ProcessHandoff).where(
                    ProcessHandoff.org_id == org_id,
                    ProcessHandoff.discovery_run_id == run_id,
                )
            )
            handoffs = handoffs_q.scalars().all()
            domain_proc_ids = {p.id for p in domain_procs}
            domain_handoffs = [
                {
                    "source": str(h.source_process_id),
                    "target": str(h.target_process_id),
                    "type": h.handoff_type,
                    "confidence": h.confidence_score,
                }
                for h in handoffs
                if h.source_process_id in domain_proc_ids or h.target_process_id in domain_proc_ids
            ]

            raw_metadata = await gather_metadata_summary(org_id, db)
            doc_chunks = await semantic_document_search(
                org_id, db, f"{domain.name}: {domain.description or ''}", limit=15
            )

            prompt = await build_stage5_prompt(
                org_id, db, complete_tree, {"handoffs": domain_handoffs}, raw_metadata, doc_chunks,
            )

            with _lf_span(f"stage5_domain_{domain.name}"):
                _result, parsed = _call_with_retry(
                    prompt=prompt, max_tokens=12000, tier="strong",
                    operation="discovery_validation",
                    label=f"stage5_{domain.name}",
                    model_config=model_config,
                )

            critique = _as_list(parsed.get("critique") or parsed.get("items"))
            all_critiques.extend(critique)

            patches = parsed.get("patches", {})
            if isinstance(patches, dict):
                name_to_proc_map = {p.name: p for p in domain_procs}

                for adj in _as_list(patches.get("confidence_adjustments")):
                    if not isinstance(adj, dict):
                        continue
                    bp = name_to_proc_map.get(str(adj.get("step_name", "")))
                    if bp and adj.get("new") is not None:
                        bp.confidence_score = float(adj["new"])
                        if bp.confidence_score < NEEDS_REVIEW_CONFIDENCE:
                            bp.needs_review = True

                for us in _as_list(patches.get("updated_steps")):
                    if not isinstance(us, dict):
                        continue
                    bp = name_to_proc_map.get(str(us.get("name", "")))
                    if not bp:
                        continue
                    for field in [
                        "trigger_conditions", "decision_logic", "system_touchpoints",
                        "success_criteria", "failure_modes", "actors",
                    ]:
                        if field in us:
                            setattr(bp, field, _as_list(us[field]))
                    for field in [
                        "value_classification", "complexity_score", "automation_potential",
                        "estimated_duration", "estimated_frequency",
                    ]:
                        if field in us:
                            setattr(bp, field, us[field])

                for step_name in _as_list(patches.get("removed_steps")):
                    bp = name_to_proc_map.get(str(step_name))
                    if bp:
                        bp.status = "rejected"

            await db.flush()

        if progress_cb:
            progress_cb("validation", "done", len(all_critiques), max(len(all_critiques), 1))

        logger.info(
            "stage5_complete org_id=%s run_id=%s issues=%d dur_ms=%d",
            org_id, run_id, len(all_critiques), int((time.time() - start) * 1000),
        )
        return {"critique": all_critiques}


async def run_stage6(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> dict:
    """Stage 6: Cross-domain synthesis. Returns parsed synthesis dict."""
    start = time.time()

    with _lf_span("stage6_cross_domain_synthesis", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("cross_domain_synthesis", "gathering", 0, 1)

        org_ctx = await gather_org_context(org_id, db)

        domains_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.level == "domain",
                BusinessProcess.status != "rejected",
            )
        )
        domains = domains_q.scalars().all()

        all_procs_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.status != "rejected",
            )
        )
        all_run_procs = all_procs_q.scalars().all()
        id_to_proc = {p.id: p for p in all_run_procs}

        all_domains_data: list[dict] = []
        for domain in domains:
            domain_procs: list[BusinessProcess] = []
            for p in all_run_procs:
                current = p
                under_domain = False
                while current:
                    if current.id == domain.id:
                        under_domain = True
                        break
                    current = id_to_proc.get(current.parent_id)
                if under_domain:
                    domain_procs.append(p)

            def build_synthesis_tree(proc: BusinessProcess) -> dict:
                return {
                    "name": proc.name,
                    "level": proc.level,
                    "description": proc.description,
                    "system_touchpoints": proc.system_touchpoints or [],
                    "trigger_conditions": proc.trigger_conditions or [],
                    "decision_logic": proc.decision_logic or [],
                    "actors": proc.actors or [],
                    "artifacts": proc.artifacts or [],
                    "sequencing": proc.sequencing or {},
                    "value_classification": proc.value_classification,
                    "children": [
                        build_synthesis_tree(c)
                        for c in domain_procs
                        if c.parent_id == proc.id
                    ],
                }

            hierarchy_roots = [
                build_synthesis_tree(p) for p in domain_procs if p.parent_id == domain.id
            ]
            all_domains_data.append({
                "name": domain.name,
                "description": domain.description,
                "processes": hierarchy_roots,
            })

        meta_summary = await gather_metadata_summary(org_id, db)
        claimed_objects: set[str] = set()
        for d in domains:
            claimed_objects.update(
                str(x) for x in _as_list((d.metadata_json or {}).get("associated_objects")) if x
            )
        objects = meta_summary.get("objects") or []
        if not isinstance(objects, list):
            objects = []
        orphaned = [
            {"type": "object", "api_name": o["api_name"]}
            for o in objects
            if isinstance(o, dict) and str(o.get("api_name", "")) not in claimed_objects
        ]

        prompt = await build_pass3_prompt(
            org_id, db, org_ctx, all_domains_data, orphaned,
        )

        result, parsed = _call_with_retry(
            prompt=prompt, max_tokens=8000, tier="strong",
            operation="discovery_synthesis", label="stage6",
            model_config=model_config,
        )

        process_name_q = await db.execute(
            select(BusinessProcess.id, BusinessProcess.name).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
            )
        )
        name_to_id = {str(row.name): row.id for row in process_name_q}

        handoff_count = 0
        for ho in _as_list(parsed.get("cross_domain_handoffs") or parsed.get("items")):
            if not isinstance(ho, dict):
                continue
            src_name = str(ho.get("source_process", ""))
            tgt_name = str(ho.get("target_process", ""))
            src_id = name_to_id.get(src_name)
            tgt_id = name_to_id.get(tgt_name)
            if src_id and tgt_id:
                confidence = float(ho.get("confidence", 0.5))
                is_gap = bool(ho.get("is_gap", False))
                db.add(
                    ProcessHandoff(
                        org_id=org_id,
                        source_process_id=src_id,
                        target_process_id=tgt_id,
                        handoff_type=str(ho.get("type", "unknown"))[:50],
                        description=ho.get("reasoning"),
                        confidence_score=confidence,
                        is_gap=is_gap,
                        needs_review=is_gap or confidence < NEEDS_REVIEW_CONFIDENCE,
                        discovery_run_id=run_id,
                        metadata_json={
                            "source_process": src_name,
                            "target_process": tgt_name,
                            "source_domain": ho.get("source_domain"),
                            "target_domain": ho.get("target_domain"),
                            "data_transferred": _as_list(ho.get("data_transferred")),
                            "transfer_mechanism": ho.get("transfer_mechanism"),
                        },
                    )
                )
                handoff_count += 1

        await db.flush()
        logger.info(
            "stage6_complete org_id=%s run_id=%s handoffs=%d orphaned=%d tokens_in=%d tokens_out=%d dur_ms=%d",
            org_id,
            run_id,
            handoff_count,
            len(orphaned),
            result.input_tokens,
            result.output_tokens,
            int((time.time() - start) * 1000),
        )

        if progress_cb:
            progress_cb("cross_domain_synthesis", "done", 1, 1)

        return parsed


async def run_stage7(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
) -> dict:
    """Stage 7: Quality Scoring. Pure computation, no LLM. Returns quality_scores dict."""
    steps_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level == "step",
            BusinessProcess.status != "rejected",
        )
    )
    steps = steps_q.scalars().all()

    objects_q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.record_count > 0,
        )
    )
    all_objects = objects_q.scalars().all()
    all_object_names = {o.api_name for o in all_objects}

    autos_q = await db.execute(
        select(MetadataAutomation).where(MetadataAutomation.org_id == org_id)
    )
    all_autos = autos_q.scalars().all()
    all_auto_names = {a.api_name for a in all_autos}
    total_artifacts = len(all_object_names) + len(all_auto_names)

    referenced_objects: set[str] = set()
    referenced_autos: set[str] = set()
    for s in steps:
        for tp in (s.system_touchpoints or []):
            if isinstance(tp, dict) and tp.get("object_api_name"):
                referenced_objects.add(tp["object_api_name"])
            if isinstance(tp, dict) and tp.get("automation_name"):
                referenced_autos.add(tp["automation_name"])
        for art in (s.artifacts or []):
            if isinstance(art, dict):
                if art.get("type") == "object":
                    referenced_objects.add(art.get("api_name", ""))
                elif art.get("type") in ("flow", "validation_rule"):
                    referenced_autos.add(art.get("api_name", ""))

    covered = len(referenced_objects & all_object_names) + len(referenced_autos & all_auto_names)
    metadata_coverage = covered / total_artifacts if total_artifacts > 0 else 0.0

    steps_with_touchpoints = sum(1 for s in steps if s.system_touchpoints)
    step_specificity = steps_with_touchpoints / len(steps) if steps else 0.0

    handoffs_q = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == run_id,
        )
    )
    handoffs = handoffs_q.scalars().all()
    grounded = sum(1 for h in handoffs if h.handoff_type not in ("unknown", "inferred"))
    handoff_grounding = grounded / len(handoffs) if handoffs else 0.0

    domains_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level == "domain",
            BusinessProcess.status != "rejected",
        )
    )
    domains = domains_q.scalars().all()
    if len(domains) > 1:
        all_run_procs_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.status != "rejected",
            )
        )
        all_run_procs = all_run_procs_q.scalars().all()
        id_to_proc = {p.id: p for p in all_run_procs}

        def get_depth(proc: BusinessProcess) -> int:
            d = 0
            current = proc
            while current and current.parent_id:
                d += 1
                current = id_to_proc.get(current.parent_id)
            return d

        depths_per_domain = []
        for dom in domains:
            max_d = 0
            for p in all_run_procs:
                current = p
                under = False
                while current:
                    if current.id == dom.id:
                        under = True
                        break
                    current = id_to_proc.get(current.parent_id)
                if under:
                    d = get_depth(p)
                    max_d = max(max_d, d)
            depths_per_domain.append(max_d)

        if len(depths_per_domain) > 1:
            mean_d = statistics.mean(depths_per_domain)
            std_d = statistics.stdev(depths_per_domain)
            hierarchy_consistency = max(0.0, 1.0 - (std_d / mean_d if mean_d > 0 else 0.0))
        else:
            hierarchy_consistency = 1.0
    else:
        hierarchy_consistency = 1.0

    steps_with_value = sum(1 for s in steps if s.value_classification)
    value_coverage = steps_with_value / len(steps) if steps else 0.0

    overall = (
        metadata_coverage * 0.25 +
        step_specificity * 0.25 +
        handoff_grounding * 0.20 +
        hierarchy_consistency * 0.15 +
        value_coverage * 0.15
    )

    quality_scores = {
        "metadata_coverage": round(metadata_coverage, 3),
        "step_specificity": round(step_specificity, 3),
        "handoff_grounding": round(handoff_grounding, 3),
        "hierarchy_consistency": round(hierarchy_consistency, 3),
        "value_coverage": round(value_coverage, 3),
        "overall": round(overall, 3),
    }

    run = await db.get(DiscoveryRun, run_id)
    if run:
        run.quality_scores = quality_scores
    await db.flush()

    logger.info("stage7_complete org_id=%s run_id=%s scores=%s", org_id, run_id, quality_scores)

    for metric, value in quality_scores.items():
        langfuse_score(name=f"discovery_{metric}", value=value)

    return quality_scores


async def cleanup_previous_run(org_id: UUID, db: AsyncSession) -> None:
    """Delete discovery-sourced rows for an org before a new run (FK-safe order)."""
    await db.execute(delete(ProcessHandoff).where(ProcessHandoff.org_id == org_id))

    discovery_proc_ids = select(BusinessProcess.id).where(
        BusinessProcess.org_id == org_id,
        BusinessProcess.source == "discovery",
    )
    await db.execute(delete(ProcessEdge).where(ProcessEdge.process_id.in_(discovery_proc_ids)))
    await db.execute(delete(ProcessNode).where(ProcessNode.process_id.in_(discovery_proc_ids)))
    await db.execute(
        delete(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.source == "discovery",
        )
    )
    await db.flush()
    logger.info("discovery_cleanup_complete org_id=%s", org_id)
