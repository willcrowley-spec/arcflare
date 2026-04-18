"""Three-pass process discovery pipeline."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Callable, Iterator
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import get_langfuse
from app.models.discovery import ProcessHandoff
from app.models.process import BusinessProcess, ProcessEdge, ProcessNode
from app.services.ai.router import LLMResult, llm_call, parse_json_response
from app.services.processes.context import (
    gather_document_chunks_for_domain,
    gather_document_summary,
    gather_metadata_for_domain,
    gather_metadata_summary,
    gather_org_context,
)
from app.services.processes.prompts import (
    build_pass1_prompt,
    build_pass2_prompt,
    build_pass3_prompt,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int, int], None] | None

NEEDS_REVIEW_CONFIDENCE = 0.6


def _discovery_trace_context(run_id: UUID) -> dict | None:
    """Stable trace_id per run so passes nest under one Langfuse trace when supported."""
    lf = get_langfuse()
    if lf is None:
        return None
    try:
        from langfuse import Langfuse

        trace_id = Langfuse.create_trace_id(seed=f"discovery-run-{run_id}")
        return {"trace_id": trace_id}
    except Exception as exc:
        logger.debug("langfuse_trace_context_failed run_id=%s error=%s", run_id, exc)
        return None


@contextmanager
def _langfuse_pass_span(
    lf,
    name: str,
    metadata: dict,
    trace_context: dict | None,
) -> Iterator[object | None]:
    """Open a Langfuse span for a pipeline pass; no-op if tracing is unavailable."""
    if lf is None:
        yield None
        return
    cm = None
    try:
        kwargs: dict = {"name": name, "as_type": "span", "metadata": metadata}
        if trace_context:
            kwargs["trace_context"] = trace_context
        cm = lf.start_as_current_observation(**kwargs)
    except TypeError:
        try:
            cm = lf.start_as_current_observation(name=name, as_type="span", metadata=metadata)
        except Exception as exc:
            logger.debug("langfuse_pass_span_start_failed name=%s error=%s", name, exc)
            yield None
            return
    except Exception as exc:
        logger.debug("langfuse_pass_span_start_failed name=%s error=%s", name, exc)
        yield None
        return
    with cm as span:
        yield span


def _empty_llm_result() -> LLMResult:
    return LLMResult(text="{}", input_tokens=0, output_tokens=0, model="", provider="")


def _finalize_span(span: object | None, extra: dict) -> None:
    if span is None:
        return
    try:
        span.update(metadata=extra)
    except Exception as exc:
        logger.debug("langfuse_span_update_failed error=%s", exc)


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


def _as_list(val: object) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [val]
    return []


async def run_pass1(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> list[dict]:
    """Pass 1: Domain Discovery. Returns list of domain dicts."""
    lf = get_langfuse()
    trace_ctx = _discovery_trace_context(run_id)
    start = time.time()
    base_meta = {"org_id": str(org_id), "run_id": str(run_id), "pass": "1"}

    with _langfuse_pass_span(lf, "pass1_domain_discovery", base_meta, trace_ctx) as span:
        if progress_cb:
            progress_cb("domain_discovery", "gathering", 0, 1)

        org_ctx = await gather_org_context(org_id, db)
        meta_summary = await gather_metadata_summary(org_id, db)
        doc_summary = await gather_document_summary(org_id, db)

        prompt = build_pass1_prompt(org_ctx, meta_summary, doc_summary)

        try:
            result = llm_call(
                prompt=prompt, max_tokens=4000, tier="strong",
                operation="discovery_domain", model_config=model_config,
            )
        except Exception as exc:
            logger.error("pass1_llm_failed org_id=%s run_id=%s error=%s", org_id, run_id, exc)
            result = _empty_llm_result()

        parsed = _safe_parse(result.text, "pass1")
        raw_domains = parsed.get("domains")
        if isinstance(raw_domains, list):
            domains = raw_domains
        else:
            if raw_domains is not None:
                logger.warning(
                    "pass1_domains_wrong_type org_id=%s type=%s",
                    org_id,
                    type(raw_domains).__name__,
                )
            domains = []

        logger.info(
            "pass1_complete org_id=%s run_id=%s domains=%d tokens_in=%d tokens_out=%d dur_ms=%d",
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

        _finalize_span(
            span,
            {
                **base_meta,
                "domains_found": len(domains),
                "duration_ms": int((time.time() - start) * 1000),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )

        if progress_cb:
            progress_cb("domain_discovery", "done", 1, 1)

        return domains


async def run_pass2(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> int:
    """Pass 2: Process decomposition per domain. Returns total process rows created."""
    lf = get_langfuse()
    trace_ctx = _discovery_trace_context(run_id)
    start = time.time()
    base_meta = {"org_id": str(org_id), "run_id": str(run_id), "pass": "2"}
    total_input_tokens = 0
    total_output_tokens = 0

    with _langfuse_pass_span(lf, "pass2_process_decomposition", base_meta, trace_ctx) as span:
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
                progress_cb("domain_decomposition", "running", i, len(domains))

            meta_json = domain.metadata_json or {}
            object_names = _as_list(meta_json.get("associated_objects"))
            automation_names = _as_list(meta_json.get("associated_automations"))
            str_objects = [str(x) for x in object_names if x]
            str_automations = [str(x) for x in automation_names if x]

            meta_detail = await gather_metadata_for_domain(
                org_id, db, str_objects, str_automations
            )
            doc_chunks = await gather_document_chunks_for_domain(
                org_id, db, f"{domain.name}: {domain.description or ''}"
            )

            domain_dict = {"name": domain.name, "description": domain.description or ""}
            prompt = build_pass2_prompt(org_ctx, domain_dict, meta_detail, doc_chunks)

            domain_meta = {
                **base_meta,
                "domain": domain.name,
                "domain_index": i,
                "domain_total": len(domains),
            }
            domain_start = time.time()
            with _langfuse_pass_span(
                lf, "pass2_domain_llm", domain_meta, trace_ctx
            ) as domain_span:
                try:
                    result = llm_call(
                        prompt=prompt, max_tokens=6000, tier="strong",
                        operation="discovery_decomposition", model_config=model_config,
                    )
                    total_input_tokens += result.input_tokens
                    total_output_tokens += result.output_tokens
                    parsed = _safe_parse(result.text, f"pass2_domain_{domain.name}")
                except Exception as exc:
                    logger.error(
                        "pass2_llm_failed org_id=%s run_id=%s domain=%s error=%s",
                        org_id,
                        run_id,
                        domain.name,
                        exc,
                    )
                    result = _empty_llm_result()
                    parsed = {}

                raw_procs = parsed.get("processes")
                if isinstance(raw_procs, list):
                    processes = raw_procs
                else:
                    if raw_procs is not None:
                        logger.warning(
                            "pass2_processes_wrong_type domain=%s type=%s",
                            domain.name,
                            type(raw_procs).__name__,
                        )
                    processes = []
                handoffs = parsed.get("handoffs")
                if isinstance(handoffs, list):
                    pass
                else:
                    if handoffs is not None:
                        logger.warning(
                            "pass2_handoffs_wrong_type domain=%s type=%s",
                            domain.name,
                            type(handoffs).__name__,
                        )
                    handoffs = []
                process_name_to_id: dict[str, UUID] = {}

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
                    process_name_to_id[str(bp.name)] = bp.id
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

                for ho in handoffs:
                    if not isinstance(ho, dict):
                        continue
                    src_id = process_name_to_id.get(str(ho.get("source", "")))
                    tgt_id = process_name_to_id.get(str(ho.get("target", "")))
                    if src_id and tgt_id:
                        confidence = float(ho.get("confidence", 0.5))
                        db.add(
                            ProcessHandoff(
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
                                    "source_name": ho.get("source"),
                                    "target_name": ho.get("target"),
                                },
                            )
                        )

                domain.sub_process_count = len(processes)
                await db.flush()

                _finalize_span(
                    domain_span,
                    {
                        **domain_meta,
                        "duration_ms": int((time.time() - domain_start) * 1000),
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "processes_persisted": len(processes),
                        "handoffs_persisted": len(
                            [h for h in handoffs if isinstance(h, dict)]
                        ),
                    },
                )

        logger.info(
            "pass2_complete org_id=%s run_id=%s processes=%d domains=%d tokens_in=%d tokens_out=%d dur_ms=%d",
            org_id,
            run_id,
            total_processes,
            len(domains),
            total_input_tokens,
            total_output_tokens,
            int((time.time() - start) * 1000),
        )

        _finalize_span(
            span,
            {
                **base_meta,
                "processes_found": total_processes,
                "domains_decomposed": len(domains),
                "duration_ms": int((time.time() - start) * 1000),
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            },
        )

        if progress_cb:
            progress_cb("domain_decomposition", "done", len(domains), len(domains))

        return total_processes


async def run_pass3(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> dict:
    """Pass 3: Cross-domain synthesis. Returns parsed synthesis dict."""
    lf = get_langfuse()
    trace_ctx = _discovery_trace_context(run_id)
    start = time.time()
    base_meta = {"org_id": str(org_id), "run_id": str(run_id), "pass": "3"}

    with _langfuse_pass_span(lf, "pass3_cross_domain_synthesis", base_meta, trace_ctx) as span:
        if progress_cb:
            progress_cb("cross_domain", "gathering", 0, 1)

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

        all_domains_data: list[dict] = []
        for domain in domains:
            children_q = await db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.parent_id == domain.id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.status != "rejected",
                )
            )
            children = children_q.scalars().all()
            all_domains_data.append(
                {
                    "name": domain.name,
                    "description": domain.description,
                    "processes": [
                        {"name": c.name, "level": c.level, "description": c.description}
                        for c in children
                    ],
                }
            )

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

        prompt = build_pass3_prompt(org_ctx, all_domains_data, orphaned)

        try:
            result = llm_call(
                prompt=prompt, max_tokens=4000, tier="strong",
                operation="discovery_synthesis", model_config=model_config,
            )
        except Exception as exc:
            logger.error("pass3_llm_failed org_id=%s run_id=%s error=%s", org_id, run_id, exc)
            result = _empty_llm_result()

        parsed = _safe_parse(result.text, "pass3")

        process_name_q = await db.execute(
            select(BusinessProcess.id, BusinessProcess.name).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
            )
        )
        name_to_id = {str(row.name): row.id for row in process_name_q}

        handoff_count = 0
        for ho in _as_list(parsed.get("cross_domain_handoffs")):
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
                        },
                    )
                )
                handoff_count += 1

        await db.flush()
        logger.info(
            "pass3_complete org_id=%s run_id=%s handoffs=%d orphaned=%d tokens_in=%d tokens_out=%d dur_ms=%d",
            org_id,
            run_id,
            handoff_count,
            len(orphaned),
            result.input_tokens,
            result.output_tokens,
            int((time.time() - start) * 1000),
        )

        _finalize_span(
            span,
            {
                **base_meta,
                "cross_domain_handoffs": handoff_count,
                "orphaned_artifacts": len(orphaned),
                "duration_ms": int((time.time() - start) * 1000),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )

        if progress_cb:
            progress_cb("cross_domain", "done", 1, 1)

        return parsed


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
