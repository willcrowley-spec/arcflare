"""Seven-stage process discovery intelligence pipeline."""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import Callable
from uuid import UUID

import litellm.exceptions as _llm_exc
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import langfuse_score, langfuse_span as _lf_span
from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.metadata import MetadataAutomation, MetadataDependency, MetadataObject
from app.models.process import BusinessProcess, ProcessEdge, ProcessNode
from app.services.ai.router import LLMResult, PromptParts, llm_call, parse_json_response
from app.services.processes.context import (
    batch_semantic_search,
    gather_dependency_subgraph,
    gather_document_summary,
    gather_metadata_for_domain,
    gather_metadata_relationships,
    gather_metadata_summary,
    gather_org_context,
    get_relevant_metadata_summaries,
    semantic_document_search,
)
from app.services.processes.visibility import (
    hidden_metadata_terms,
    metadata_object_visible_clause,
    redact_hidden_metadata_text,
    text_mentions_hidden_metadata,
)
from app.services.processes.prompts import (
    build_pass1_prompt,
    build_pass3_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    build_stage3_4_prompt,
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


TOKEN_BUDGET_LIMIT = 100_000


_RETRYABLE_ERRORS = (
    _llm_exc.RateLimitError,
    _llm_exc.InternalServerError,
    _llm_exc.ServiceUnavailableError,
    _llm_exc.APIConnectionError,
)
_BACKOFF_CAP = 60


def _call_with_retry(
    prompt: str | PromptParts,
    max_tokens: int,
    tier: str,
    operation: str,
    label: str,
    model_config: dict | None = None,
    retries: int = 4,
    budget_multiplier: float = 1.5,
) -> tuple[LLMResult, dict]:
    """LLM call with retry for transient errors and JSON parse failures.

    Retry policy (per industry best practice):
      - Only retries 429 (rate limit) and 5xx (server) errors.
      - Reads ``retry-after`` header when available; otherwise uses full
        jitter exponential backoff: ``random(0, min(cap, base * 2^attempt))``.
      - 400/401/403 errors fail immediately (non-retryable).
      - JSON parse failures retry with a larger ``max_tokens`` budget.
    """
    import random as _random
    import time as _time

    flat = prompt.as_flat() if isinstance(prompt, PromptParts) else prompt
    est = _estimate_tokens(flat)
    if est > TOKEN_BUDGET_LIMIT:
        logger.warning(
            "prompt_truncated label=%s est_tokens=%d limit=%d",
            label, est, TOKEN_BUDGET_LIMIT,
        )
        char_limit = TOKEN_BUDGET_LIMIT * 4
        truncated = flat[:char_limit]
        last_section = truncated.rfind("\n## ")
        if last_section > char_limit // 2:
            truncated = truncated[:last_section]
        prompt = truncated

    for attempt in range(1 + retries):
        tokens = int(max_tokens * (budget_multiplier ** attempt))
        try:
            result = llm_call(
                prompt=prompt, max_tokens=tokens, tier=tier,
                operation=operation, model_config=model_config,
            )
        except Exception as exc:
            is_retryable = isinstance(exc, _RETRYABLE_ERRORS)
            is_rate_limit = isinstance(exc, _llm_exc.RateLimitError)

            logger.error(
                "llm_call_failed label=%s attempt=%d retryable=%s error=%s",
                label, attempt + 1, is_retryable, exc,
            )

            if not is_retryable or attempt >= retries:
                return _empty_llm_result(), {}

            retry_after = getattr(exc, "retry_after", None) or getattr(exc, "retry_after_ms", None)
            if retry_after is not None:
                wait = float(retry_after)
                if wait > 1000:
                    wait = wait / 1000.0
                wait = min(wait, _BACKOFF_CAP)
                logger.info("rate_limit_retry_after label=%s wait=%.1fs", label, wait)
            elif is_rate_limit:
                wait = min(_BACKOFF_CAP, 8 * (2 ** attempt)) + _random.uniform(0, 2)
                logger.info("rate_limit_jitter_backoff label=%s wait=%.1fs", label, wait)
            else:
                wait = min(_BACKOFF_CAP, 2 * (2 ** attempt)) + _random.uniform(0, 1)

            _time.sleep(wait)
            continue

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


def _text(val: object) -> str:
    return str(val or "").strip()


def _normalize_v2_fields(raw_fields: object, object_api_name: str) -> list[str]:
    fields: list[str] = []
    for item in _as_list(raw_fields):
        if isinstance(item, dict):
            value = _text(item.get("api_name") or item.get("field_api_name") or item.get("name"))
        else:
            value = _text(item)
        if not value:
            continue
        if "." in value:
            obj_part, field_part = value.split(".", 1)
            if not object_api_name or obj_part.lower() == object_api_name.lower():
                value = field_part
        fields.append(value)
    return sorted(dict.fromkeys(fields))


def _normalize_v2_touchpoint(raw: object) -> dict | None:
    """Normalize LLM touchpoints into the canonical persisted process shape.

    The strict extraction schema emits a compact `{name, type, operation, fields}`
    shape. Downstream binding code also understands `object_api_name` and
    `automation_name`, so add those deterministic aliases here instead of making
    later stages infer them from prose.
    """
    if isinstance(raw, str):
        name = _text(raw)
        if not name:
            return None
        if "." in name:
            obj, field = name.split(".", 1)
            return {
                "name": obj,
                "type": "object",
                "operation": "read",
                "fields": [field],
                "object_api_name": obj,
                "evidence_refs": [],
            }
        return {
            "name": name,
            "type": "object",
            "operation": "read",
            "fields": [],
            "object_api_name": name,
            "evidence_refs": [],
        }

    if not isinstance(raw, dict):
        return None

    kind = _text(raw.get("type") or raw.get("ref_type")).lower()
    name = _text(
        raw.get("name")
        or raw.get("api_name")
        or raw.get("object_api_name")
        or raw.get("automation_name")
        or raw.get("component_api_name")
    )
    if not name:
        return None

    if kind in {"sobject", "metadata_object"}:
        kind = "object"
    elif kind in {"flow", "workflow_rule", "apex_trigger", "validation_rule", "approval_process"}:
        kind = "automation"
    elif kind in {"apex", "apex_class", "prompt"}:
        kind = "component"
    elif kind in {"external_system", "external", "api", "queue", "schema_mapping"}:
        kind = "integration"
    elif kind not in {"object", "automation", "component", "integration"}:
        kind = "object"

    operation = _text(raw.get("operation")) or ("trigger" if kind == "automation" else "read")
    if operation == "update":
        operation = "write"
    if operation not in {"read", "write", "create", "trigger"}:
        operation = "read" if kind == "object" else "trigger"

    fields = _normalize_v2_fields(raw.get("fields"), name if kind == "object" else "")
    out = {
        **raw,
        "name": name,
        "type": kind,
        "operation": operation,
        "fields": fields,
        "evidence_refs": [_text(r) for r in _as_list(raw.get("evidence_refs")) if _text(r)],
    }
    if kind == "object":
        out["object_api_name"] = name
    elif kind == "automation":
        out["automation_name"] = name
    else:
        out["api_name"] = name
    return out


def _normalize_v2_process_node(raw: object, *, is_child: bool = False) -> dict | None:
    if not isinstance(raw, dict):
        return None
    node = dict(raw)
    node["name"] = _text(node.get("name")) or "Unnamed"
    node["level"] = "step" if is_child else "process"
    node["evidence_refs"] = [_text(r) for r in _as_list(node.get("evidence_refs")) if _text(r)]
    node["actors"] = _as_list(node.get("actors"))
    node["trigger_conditions"] = _as_list(node.get("trigger_conditions"))
    node["system_touchpoints"] = [
        tp for tp in (_normalize_v2_touchpoint(tp) for tp in _as_list(node.get("system_touchpoints")))
        if tp is not None
    ]
    if not node["system_touchpoints"]:
        node["needs_review"] = True
        try:
            node["confidence"] = min(float(node.get("confidence", 0.5)), 0.59)
        except (TypeError, ValueError):
            node["confidence"] = 0.5
    node["decision_logic"] = _as_list(node.get("decision_logic"))
    node["success_criteria"] = _as_list(node.get("success_criteria"))
    node["failure_modes"] = _as_list(node.get("failure_modes"))
    if not is_child:
        node["children"] = [
            child
            for child in (_normalize_v2_process_node(c, is_child=True) for c in _as_list(node.get("children")))
            if child is not None
        ]
    return node


def _normalize_v2_extraction_result(parsed: dict) -> dict:
    result = dict(parsed or {})
    result["processes"] = [
        proc
        for proc in (_normalize_v2_process_node(p) for p in _as_list(result.get("processes")))
        if proc is not None
    ]
    result["intra_domain_handoffs"] = _as_list(result.get("intra_domain_handoffs"))
    return result


def _node_mentions_hidden_metadata(node: dict, hidden_terms: set[str]) -> bool:
    if not hidden_terms:
        return False
    fields = [
        node.get("name"),
        node.get("description"),
        node.get("narrative"),
        node.get("system_touchpoints"),
        node.get("trigger_conditions"),
        node.get("decision_logic"),
    ]
    if any(text_mentions_hidden_metadata(str(field or ""), hidden_terms) for field in fields):
        return True
    for touchpoint in _as_list(node.get("system_touchpoints")):
        if not isinstance(touchpoint, dict):
            continue
        touchpoint_refs = [
            touchpoint.get("object_api_name"),
            touchpoint.get("name"),
            touchpoint.get("api_name"),
            touchpoint.get("fields"),
        ]
        if any(
            text_mentions_hidden_metadata(f"Object: {ref}", hidden_terms)
            for ref in touchpoint_refs
            if ref
        ):
            return True
    return False


def _drop_hidden_v2_nodes(parsed: dict, hidden_terms: set[str]) -> dict:
    """Remove extracted process nodes that mention excluded metadata."""
    if not hidden_terms:
        return parsed
    result = dict(parsed or {})
    filtered_processes: list[dict] = []
    for proc in _as_list(result.get("processes")):
        if not isinstance(proc, dict) or _node_mentions_hidden_metadata(proc, hidden_terms):
            continue
        kept_children = [
            child
            for child in _as_list(proc.get("children"))
            if isinstance(child, dict)
            and not _node_mentions_hidden_metadata(child, hidden_terms)
        ]
        if not kept_children:
            continue
        filtered = dict(proc)
        filtered["children"] = kept_children
        filtered_processes.append(filtered)
    result["processes"] = filtered_processes
    return result


def _v2_extraction_contract_issues(parsed: dict) -> list[str]:
    """Return blocking shape issues that must not be persisted as good data."""
    issues: list[str] = []
    processes = _as_list(parsed.get("processes"))
    if not processes:
        return ["no_processes"]

    for proc_idx, proc in enumerate(processes):
        if not isinstance(proc, dict):
            issues.append(f"process[{proc_idx}]:not_object")
            continue
        label = _text(proc.get("name")) or f"process[{proc_idx}]"
        for key in ("evidence_refs", "actors", "trigger_conditions"):
            if not _as_list(proc.get(key)):
                issues.append(f"{label}:missing_{key}")
        children = _as_list(proc.get("children"))
        if not children:
            issues.append(f"{label}:missing_child_steps")
            continue
        for child_idx, child in enumerate(children):
            if not isinstance(child, dict):
                issues.append(f"{label}.child[{child_idx}]:not_object")
                continue
            child_label = _text(child.get("name")) or f"{label}.child[{child_idx}]"
            if child.get("level") != "step":
                issues.append(f"{child_label}:child_must_be_step")
            for key in ("evidence_refs", "actors", "trigger_conditions"):
                if not _as_list(child.get(key)):
                    issues.append(f"{child_label}:missing_{key}")
    return issues[:20]


async def _async_llm_call(**kwargs) -> tuple[LLMResult, dict]:
    """Run _call_with_retry in a thread with adaptive rate limiting.

    Gates on input tokens only.  Output token limits are handled reactively
    via 429 backoff in ``_call_with_retry`` -- pre-booking output tokens
    causes deadlock when many domains queue against a tiny output window.
    """
    from app.services.ai.rate_limiter import get_limiter
    from app.services.ai.operations import resolve_model

    operation = kwargs.get("operation", "")
    tier = kwargs.get("tier", "fast")
    model = resolve_model(
        operation=operation,
        tier=tier,
        model_config=kwargs.get("model_config"),
    )
    limiter = get_limiter(model)

    prompt_val = kwargs.get("prompt", "")
    flat_text = prompt_val.as_flat() if isinstance(prompt_val, PromptParts) else prompt_val
    est_input = _estimate_tokens(flat_text)
    await limiter.acquire(est_input)

    return await asyncio.to_thread(_call_with_retry, **kwargs)


def _estimate_tokens(text: str) -> int:
    """Rough token count (chars / 4). Good enough for budget checks."""
    return len(text) // 4


def _get_procs_under_domain(
    domain_id: UUID,
    all_procs: list[BusinessProcess],
    id_to_proc: dict[UUID, BusinessProcess],
) -> list[BusinessProcess]:
    """Filter all_procs to those that are descendants of domain_id."""
    result = []
    for p in all_procs:
        current = p
        while current:
            if current.id == domain_id:
                result.append(p)
                break
            current = id_to_proc.get(current.parent_id)
    return result


# ---------------------------------------------------------------------------
# DEPRECATED v1 PIPELINE — not invoked by any worker or API route.
# Retained temporarily for reference; will be removed in a future PR.
# The active pipeline is the run_v2_phase* family below.
# ---------------------------------------------------------------------------


async def run_stage1(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
    meta_summary: dict | None = None,
) -> tuple[list[dict], dict, dict]:
    """Stage 1: Domain Discovery. Returns (domain_dicts, org_ctx, meta_summary)."""
    start = time.time()

    with _lf_span("stage1_domain_discovery", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("domain_discovery", "gathering", 0, 1)

        org_ctx = await gather_org_context(org_id, db)
        if meta_summary is None:
            meta_summary = await gather_metadata_summary(org_id, db)
        org_desc = org_ctx.get("description") or org_ctx.get("name", "")
        doc_chunks = await semantic_document_search(org_id, db, org_desc, limit=20)
        doc_index = await gather_document_summary(org_id, db)
        tech_modules = await get_relevant_metadata_summaries(org_id, db, org_desc, limit=5)

        prompt = await build_pass1_prompt(
            org_id, db, org_ctx, meta_summary, doc_chunks,
            document_index=doc_index, technical_modules=tech_modules,
        )

        result, parsed = await asyncio.to_thread(
            _call_with_retry,
            prompt=prompt, max_tokens=8000, tier="strong",
            operation="discovery_domain", label="stage1",
            model_config=model_config,
        )

        raw_domains = parsed.get("domains")
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

        return domains, org_ctx, meta_summary


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
        import uuid as _uuid_mod

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

        domain_meta_details: list[dict] = []
        domain_queries: list[str] = []
        for domain in domains:
            meta_json = domain.metadata_json or {}
            object_names = _as_list(meta_json.get("associated_objects"))
            automation_names = _as_list(meta_json.get("associated_automations"))
            str_objects = [str(x) for x in object_names if x]
            str_automations = [str(x) for x in automation_names if x]

            meta_detail = await gather_metadata_for_domain(
                org_id, db, str_objects, str_automations
            )
            domain_meta_details.append(meta_detail)
            domain_queries.append(f"{domain.name}: {domain.description or ''}")

        all_doc_chunks = await batch_semantic_search(org_id, db, domain_queries, limit=20)

        domain_meta_modules: list[list[dict]] = []
        for query in domain_queries:
            modules = await get_relevant_metadata_summaries(org_id, db, query, limit=3)
            domain_meta_modules.append(modules)

        domain_contexts: list[tuple[BusinessProcess, dict, list[dict], list[dict]]] = []
        for i, domain in enumerate(domains):
            doc_chunks = all_doc_chunks[i] if i < len(all_doc_chunks) else []
            modules = domain_meta_modules[i] if i < len(domain_meta_modules) else []
            domain_contexts.append((domain, domain_meta_details[i], doc_chunks, modules))

        domain_prompts: list[tuple[BusinessProcess, str]] = []
        for domain, meta_detail, doc_chunks, modules in domain_contexts:
            domain_dict = {"name": domain.name, "description": domain.description or ""}
            prompt = await build_stage2_prompt(
                org_id, db, org_ctx, domain_dict, meta_detail, doc_chunks,
                metadata_modules=modules,
            )
            domain_prompts.append((domain, prompt))

        if progress_cb:
            progress_cb("structural_decomposition", "running", 0, len(domains))

        async def _decompose_domain(domain: BusinessProcess, prompt: str) -> tuple[LLMResult, dict]:
            return await _async_llm_call(
                prompt=prompt, max_tokens=8000, tier="strong",
                operation="discovery_structure",
                label=f"stage2_domain_{domain.name}",
                model_config=model_config,
            )

        llm_results = await asyncio.gather(
            *[_decompose_domain(d, p) for d, p in domain_prompts]
        )

        for i, ((domain, _prompt), (result, parsed)) in enumerate(zip(domain_prompts, llm_results)):
            total_input_tokens += result.input_tokens
            total_output_tokens += result.output_tokens

            raw_procs = parsed.get("processes")
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

            name_to_id: dict[str, UUID] = {}

            for proc_data in processes:
                if not isinstance(proc_data, dict):
                    continue
                name = str(proc_data.get("name", "Unnamed"))[:255]
                parent_name = proc_data.get("parent_name")
                if parent_name and str(parent_name) in name_to_id:
                    parent_id = name_to_id[str(parent_name)]
                else:
                    parent_id = domain.id

                pre_id = _uuid_mod.uuid4()
                confidence = float(proc_data.get("confidence", 0.5))
                bp = BusinessProcess(
                    id=pre_id,
                    org_id=org_id,
                    name=name,
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
                name_to_id[name] = pre_id
                total_processes += 1

            domain.sub_process_count = len(name_to_id)

            if progress_cb:
                progress_cb("structural_decomposition", "running", i + 1, len(domains))

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


async def run_stage3_4(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> tuple[int, int]:
    """Stage 3+4 merged: Enrichment + Flow in a single LLM pass per domain.

    Returns (enriched_count, handoff_count).
    """
    start = time.time()
    enriched_count = 0
    total_handoffs = 0

    with _lf_span("stage3_4_enrichment_flow", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
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

        all_procs_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.status != "rejected",
            )
        )
        all_procs = all_procs_q.scalars().all()
        id_to_proc = {p.id: p for p in all_procs}

        domain_payloads: list[tuple[BusinessProcess, list[BusinessProcess], str]] = []

        for domain in domains:
            domain_procs = _get_procs_under_domain(domain.id, all_procs, id_to_proc)
            domain_steps = [p for p in domain_procs if p.level == "step"]

            if not domain_steps:
                continue

            all_obj_names: set[str] = set()
            all_auto_names: set[str] = set()
            for step in domain_steps:
                for a in (step.artifacts or []):
                    if a.get("type") == "object":
                        all_obj_names.add(a.get("api_name", ""))
                    elif a.get("type") in ("flow", "validation_rule"):
                        all_auto_names.add(a.get("api_name", ""))
            for p in domain_procs:
                for tp in (p.system_touchpoints or []):
                    if isinstance(tp, dict) and tp.get("object_api_name"):
                        all_obj_names.add(tp["object_api_name"])
                for art in (p.artifacts or []):
                    if isinstance(art, dict) and art.get("type") == "object":
                        all_obj_names.add(art.get("api_name", ""))

            domain_meta = await gather_metadata_for_domain(
                org_id, db, list(all_obj_names), list(all_auto_names)
            )
            obj_meta_by_name = {o["api_name"]: o for o in domain_meta.get("objects", [])}
            auto_meta_by_name = {a["api_name"]: a for a in domain_meta.get("automations", [])}

            steps_data = []
            metadata_per_step: dict[str, dict] = {}
            docs_per_step: dict[str, list[dict]] = {}

            for step in domain_steps:
                step_artifacts = step.artifacts or []
                step_objs = [a.get("api_name", "") for a in step_artifacts if a.get("type") == "object"]
                step_autos = [a.get("api_name", "") for a in step_artifacts if a.get("type") in ("flow", "validation_rule")]
                metadata_per_step[step.name] = {
                    "objects": [obj_meta_by_name[n] for n in step_objs if n in obj_meta_by_name],
                    "automations": [auto_meta_by_name[n] for n in step_autos if n in auto_meta_by_name],
                }
                docs = await semantic_document_search(
                    org_id, db, f"{step.name}: {step.description or ''}", limit=5
                )
                docs_per_step[step.name] = docs
                steps_data.append({
                    "name": step.name,
                    "description": step.description,
                    "artifacts": step_artifacts,
                })

            def build_tree_dict(proc: BusinessProcess, _dp: list = domain_procs) -> dict:
                return {
                    "name": proc.name,
                    "level": proc.level,
                    "description": proc.description,
                    "system_touchpoints": proc.system_touchpoints or [],
                    "trigger_conditions": proc.trigger_conditions or [],
                    "actors": proc.actors or [],
                    "children": [
                        build_tree_dict(c, _dp) for c in _dp if c.parent_id == proc.id
                    ],
                }

            enriched_tree = [
                build_tree_dict(p, domain_procs) for p in domain_procs if p.parent_id == domain.id
            ]

            relationships = await gather_metadata_relationships(org_id, db, list(all_obj_names))
            dep_graph = await gather_dependency_subgraph(org_id, db, list(all_obj_names))

            prompt = await build_stage3_4_prompt(
                org_id, db, steps_data, metadata_per_step, docs_per_step,
                enriched_tree, relationships, dep_graph,
            )
            domain_payloads.append((domain, domain_procs, prompt))

        async def _enrich_flow_domain(domain: BusinessProcess, prompt) -> tuple[LLMResult, dict]:
            return await _async_llm_call(
                prompt=prompt, max_tokens=20000, tier="strong",
                operation="discovery_enrichment_flow",
                label=f"stage3_4_{domain.name}",
                model_config=model_config,
            )

        llm_results = await asyncio.gather(
            *[_enrich_flow_domain(d, p) for d, _dp, p in domain_payloads]
        )

        for (domain, domain_procs, _prompt), (_result, parsed) in zip(domain_payloads, llm_results):
            domain_steps = [p for p in domain_procs if p.level == "step"]
            name_to_step = {s.name: s for s in domain_steps}
            name_to_id: dict[str, UUID] = {p.name: p.id for p in domain_procs}
            name_to_proc: dict[str, BusinessProcess] = {p.name: p for p in domain_procs}

            for es in _as_list(parsed.get("enriched_steps")):
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

            step_flows = _as_list(parsed.get("step_flows"))
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
            progress_cb("step_enrichment", "done", enriched_count, max(enriched_count, 1))
            progress_cb("flow_analysis", "done", total_handoffs, max(total_handoffs, 1))

        logger.info(
            "stage3_4_complete org_id=%s run_id=%s enriched=%d handoffs=%d dur_ms=%d",
            org_id, run_id, enriched_count, total_handoffs, int((time.time() - start) * 1000),
        )
        return enriched_count, total_handoffs


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

        all_procs_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.status != "rejected",
            )
        )
        all_procs = all_procs_q.scalars().all()
        id_to_proc = {p.id: p for p in all_procs}

        domain_payloads: list[tuple[BusinessProcess, list[BusinessProcess], str]] = []

        for domain in domains:
            domain_steps = [
                p for p in _get_procs_under_domain(domain.id, all_procs, id_to_proc)
                if p.level == "step"
            ]

            if not domain_steps:
                continue

            all_obj_names: set[str] = set()
            all_auto_names: set[str] = set()
            for step in domain_steps:
                for a in (step.artifacts or []):
                    if a.get("type") == "object":
                        all_obj_names.add(a.get("api_name", ""))
                    elif a.get("type") in ("flow", "validation_rule"):
                        all_auto_names.add(a.get("api_name", ""))

            domain_meta = await gather_metadata_for_domain(
                org_id, db, list(all_obj_names), list(all_auto_names)
            )
            obj_meta_by_name = {o["api_name"]: o for o in domain_meta.get("objects", [])}
            auto_meta_by_name = {a["api_name"]: a for a in domain_meta.get("automations", [])}

            steps_data = []
            metadata_per_step: dict[str, dict] = {}
            docs_per_step: dict[str, list[dict]] = {}

            for step in domain_steps:
                step_artifacts = step.artifacts or []
                step_objs = [a.get("api_name", "") for a in step_artifacts if a.get("type") == "object"]
                step_autos = [a.get("api_name", "") for a in step_artifacts if a.get("type") in ("flow", "validation_rule")]
                metadata_per_step[step.name] = {
                    "objects": [obj_meta_by_name[n] for n in step_objs if n in obj_meta_by_name],
                    "automations": [auto_meta_by_name[n] for n in step_autos if n in auto_meta_by_name],
                }

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
            domain_payloads.append((domain, domain_steps, prompt))

        async def _enrich_domain(domain: BusinessProcess, prompt: str) -> tuple[LLMResult, dict]:
            return await _async_llm_call(
                prompt=prompt, max_tokens=12000, tier="strong",
                operation="discovery_enrichment",
                label=f"stage3_{domain.name}",
                model_config=model_config,
            )

        llm_results = await asyncio.gather(
            *[_enrich_domain(d, p) for d, _steps, p in domain_payloads]
        )

        for (domain, domain_steps, _prompt), (_result, parsed) in zip(domain_payloads, llm_results):

            enriched_steps = _as_list(parsed.get("enriched_steps"))
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

        all_procs_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.status != "rejected",
            )
        )
        all_procs = all_procs_q.scalars().all()
        id_to_proc = {p.id: p for p in all_procs}

        s4_payloads: list[tuple[BusinessProcess, list[BusinessProcess], str]] = []

        for domain in domains:
            domain_procs = _get_procs_under_domain(domain.id, all_procs, id_to_proc)

            if not domain_procs:
                continue

            def build_tree_dict(proc: BusinessProcess, _dp: list = domain_procs) -> dict:
                return {
                    "name": proc.name,
                    "level": proc.level,
                    "description": proc.description,
                    "system_touchpoints": proc.system_touchpoints or [],
                    "trigger_conditions": proc.trigger_conditions or [],
                    "actors": proc.actors or [],
                    "children": [
                        build_tree_dict(c, _dp) for c in _dp if c.parent_id == proc.id
                    ],
                }

            enriched_tree = [
                build_tree_dict(p, domain_procs) for p in domain_procs if p.parent_id == domain.id
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
            dep_graph = await gather_dependency_subgraph(org_id, db, list(all_objects))
            prompt = await build_stage4_prompt(
                org_id, db, enriched_tree, relationships, dependency_graph=dep_graph,
            )
            s4_payloads.append((domain, domain_procs, prompt))

        async def _flow_domain(domain: BusinessProcess, prompt: str) -> tuple[LLMResult, dict]:
            return await _async_llm_call(
                prompt=prompt, max_tokens=10000, tier="strong",
                operation="discovery_flow",
                label=f"stage4_{domain.name}",
                model_config=model_config,
            )

        s4_results = await asyncio.gather(
            *[_flow_domain(d, p) for d, _dp, p in s4_payloads]
        )

        for (domain, domain_procs, _prompt), (_result, parsed) in zip(s4_payloads, s4_results):
            name_to_id: dict[str, UUID] = {p.name: p.id for p in domain_procs}
            name_to_proc: dict[str, BusinessProcess] = {p.name: p for p in domain_procs}

            step_flows = _as_list(parsed.get("step_flows"))
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
    meta_summary: dict | None = None,
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

        all_procs_q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.status != "rejected",
            )
        )
        all_procs = all_procs_q.scalars().all()
        id_to_proc = {p.id: p for p in all_procs}

        handoffs_q = await db.execute(
            select(ProcessHandoff).where(
                ProcessHandoff.org_id == org_id,
                ProcessHandoff.discovery_run_id == run_id,
            )
        )
        all_handoffs = handoffs_q.scalars().all()

        if meta_summary is None:
            meta_summary = await gather_metadata_summary(org_id, db)
        capped_metadata = {
            "objects": meta_summary.get("objects", [])[:80],
            "automations": meta_summary.get("automations", [])[:80],
            "components": meta_summary.get("components", [])[:40],
            "totals": meta_summary.get("totals", {}),
        }

        all_id_to_name = {p.id: p.name for p in all_procs}
        s5_payloads: list[tuple[BusinessProcess, list[BusinessProcess], str]] = []

        for domain in domains:
            domain_procs = _get_procs_under_domain(domain.id, all_procs, id_to_proc)

            if not domain_procs:
                continue

            def build_complete_tree(proc: BusinessProcess, _dp: list = domain_procs) -> dict:
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
                        build_complete_tree(c, _dp)
                        for c in _dp if c.parent_id == proc.id
                    ],
                }

            complete_tree = [
                build_complete_tree(p, domain_procs) for p in domain_procs if p.parent_id == domain.id
            ]

            domain_proc_ids = {p.id for p in domain_procs}
            domain_handoffs = [
                {
                    "source": all_id_to_name.get(h.source_process_id, str(h.source_process_id)),
                    "target": all_id_to_name.get(h.target_process_id, str(h.target_process_id)),
                    "type": h.handoff_type,
                    "confidence": h.confidence_score,
                }
                for h in all_handoffs
                if h.source_process_id in domain_proc_ids or h.target_process_id in domain_proc_ids
            ]

            raw_metadata = capped_metadata
            doc_chunks = await semantic_document_search(
                org_id, db, f"{domain.name}: {domain.description or ''}", limit=15
            )

            prompt = await build_stage5_prompt(
                org_id, db, complete_tree, {"handoffs": domain_handoffs}, raw_metadata, doc_chunks,
            )
            s5_payloads.append((domain, domain_procs, prompt))

        async def _validate_domain(domain: BusinessProcess, prompt: str) -> tuple[LLMResult, dict]:
            return await _async_llm_call(
                prompt=prompt, max_tokens=12000, tier="strong",
                operation="discovery_validation",
                label=f"stage5_{domain.name}",
                model_config=model_config,
            )

        s5_results = await asyncio.gather(
            *[_validate_domain(d, p) for d, _dp, p in s5_payloads]
        )

        for (domain, domain_procs, _prompt), (_result, parsed) in zip(s5_payloads, s5_results):
            critique = _as_list(parsed.get("critique"))
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
    meta_summary: dict | None = None,
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

        if meta_summary is None:
            meta_summary = await gather_metadata_summary(org_id, db)
        claimed_objects: set[str] = set()
        claimed_automations: set[str] = set()
        for d in domains:
            dmeta = d.metadata_json or {}
            claimed_objects.update(
                str(x) for x in _as_list(dmeta.get("associated_objects")) if x
            )
            claimed_automations.update(
                str(x) for x in _as_list(dmeta.get("associated_automations")) if x
            )
        objects = meta_summary.get("objects") or []
        if not isinstance(objects, list):
            objects = []
        automations = meta_summary.get("automations") or []
        if not isinstance(automations, list):
            automations = []
        orphaned = [
            {"type": "object", "api_name": o["api_name"]}
            for o in objects
            if isinstance(o, dict) and str(o.get("api_name", "")) not in claimed_objects
        ] + [
            {"type": "automation", "api_name": a["api_name"]}
            for a in automations
            if isinstance(a, dict) and str(a.get("api_name", "")) not in claimed_automations
        ]

        prompt = await build_pass3_prompt(
            org_id, db, org_ctx, all_domains_data, orphaned,
        )

        result, parsed = await asyncio.to_thread(
            _call_with_retry,
            prompt=prompt, max_tokens=12000, tier="strong",
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

    steps_with_flow = sum(
        1 for s in steps
        if (s.sequencing or {}).get("predecessors") or (s.sequencing or {}).get("is_entry_point")
    )
    flow_completeness = steps_with_flow / len(steps) if steps else 0.0

    min_desc_len = 20
    steps_with_desc = sum(1 for s in steps if s.description and len(s.description) >= min_desc_len)
    description_quality = steps_with_desc / len(steps) if steps else 0.0

    overall = (
        metadata_coverage * 0.20 +
        step_specificity * 0.20 +
        handoff_grounding * 0.15 +
        hierarchy_consistency * 0.10 +
        value_coverage * 0.10 +
        flow_completeness * 0.15 +
        description_quality * 0.10
    )

    quality_scores = {
        "metadata_coverage": round(metadata_coverage, 3),
        "step_specificity": round(step_specificity, 3),
        "handoff_grounding": round(handoff_grounding, 3),
        "hierarchy_consistency": round(hierarchy_consistency, 3),
        "value_coverage": round(value_coverage, 3),
        "flow_completeness": round(flow_completeness, 3),
        "description_quality": round(description_quality, 3),
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


async def run_v2_phase1(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> tuple[list[dict], dict]:
    """v2 Phase 1: Domain Discovery with key_objects and key_terms.

    Returns (domain_dicts, org_ctx).
    """
    start = time.time()

    with _lf_span("v2_phase1_domain_discovery", metadata={"org_id": str(org_id), "run_id": str(run_id)}):
        if progress_cb:
            progress_cb("domain_discovery", "gathering", 0, 1)

        org_ctx = await gather_org_context(org_id, db)

        objects_q = await db.execute(
            select(MetadataObject).where(
                MetadataObject.org_id == org_id,
                MetadataObject.record_count > 0,
                metadata_object_visible_clause(),
            ).order_by(MetadataObject.record_count.desc())
        )
        object_inventory = [
            {"api_name": o.api_name, "label": o.label, "record_count": o.record_count}
            for o in objects_q.scalars().all()
        ]

        org_desc = org_ctx.get("description") or org_ctx.get("name", "")
        hidden_terms = await hidden_metadata_terms(org_id, db)
        meta_summaries = await get_relevant_metadata_summaries(
            org_id, db, org_desc, limit=10, prefer_level=0,
        )
        meta_summaries = [
            {**summary, "summary": redacted}
            for summary in meta_summaries
            for redacted in [redact_hidden_metadata_text(summary.get("summary", ""), hidden_terms)]
            if redacted
        ]

        from app.models.document import Document
        doc_summaries: list[dict] = []
        try:
            async with db.begin_nested():
                dq = await db.execute(
                    select(Document).where(
                        Document.org_id == org_id,
                        Document.summary.isnot(None),
                        Document.status == "indexed",
                    ).limit(10)
                )
                doc_summaries = [
                    {"label": d.filename, "summary": redacted}
                    for d in dq.scalars().all()
                    for redacted in [redact_hidden_metadata_text(d.summary or "", hidden_terms)]
                    if redacted
                ]
        except Exception:
            logger.warning("v2_phase1_doc_summary_failed", exc_info=True)

        from app.services.processes.prompts import build_v2_phase1_prompt
        prompt = await build_v2_phase1_prompt(
            org_id, db, org_ctx, object_inventory, meta_summaries, doc_summaries,
        )

        result, parsed = await asyncio.to_thread(
            _call_with_retry,
            prompt=prompt, max_tokens=4000, tier="strong",
            operation="discovery_v2_domain", label="v2_phase1",
            model_config=model_config,
        )

        domains = parsed.get("domains", [])
        if not isinstance(domains, list):
            domains = []

        logger.info(
            "v2_phase1_complete org_id=%s run_id=%s domains=%d tokens_in=%d tokens_out=%d dur_ms=%d",
            org_id, run_id, len(domains),
            result.input_tokens, result.output_tokens,
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
                metadata_json={
                    "key_objects": _as_list(domain.get("key_objects")),
                    "key_terms": _as_list(domain.get("key_terms")),
                },
            )
            db.add(proc)

        await db.flush()

        if progress_cb:
            progress_cb("domain_discovery", "done", 1, 1)

        return domains, org_ctx


async def run_v2_phase2(
    org_id: UUID,
    db: AsyncSession,
    domains: list[dict],
    progress_cb: ProgressCallback = None,
) -> list:
    """v2 Phase 2: Evidence Assembly (no LLM). Returns list of EvidenceBundles."""
    from app.services.processes.evidence import assemble_evidence_bundle, EvidenceBundle

    if progress_cb:
        progress_cb("evidence_assembly", "gathering", 0, len(domains))

    bundles: list[EvidenceBundle] = []
    for i, domain in enumerate(domains):
        bundle = await assemble_evidence_bundle(org_id, db, domain)
        bundles.append(bundle)
        logger.info(
            "v2_phase2_bundle domain=%s items=%d edges=%d",
            domain.get("name", "?"), len(bundle.items), len(bundle.dependency_edges),
        )
        if progress_cb:
            progress_cb("evidence_assembly", "gathering", i + 1, len(domains))

    if progress_cb:
        progress_cb("evidence_assembly", "done", len(domains), len(domains))

    return bundles


async def run_v2_phase3(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    domains: list[dict],
    bundles: list,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
    concurrency: int = 8,
) -> list[dict]:
    """v2 Phase 3: Per-domain extraction in parallel. Returns list of extraction results."""
    from app.services.processes.prompts import build_v2_phase3_prompt

    if progress_cb:
        progress_cb("extraction", "running", 0, len(domains))

    limit = max(1, int(concurrency or 1))
    semaphore = asyncio.Semaphore(limit)
    prompt_lock = asyncio.Lock()
    hidden_terms_for_run = await hidden_metadata_terms(org_id, db)

    async def _extract_domain(domain: dict, bundle) -> dict:
        async with semaphore:
            evidence_text = bundle.as_tagged_text()
            if not evidence_text.strip():
                logger.warning("v2_phase3_empty_bundle domain=%s", domain.get("name", "?"))
                return {"processes": [], "domain": domain}

            async with prompt_lock:
                prompt = await build_v2_phase3_prompt(org_id, db, domain, evidence_text)
            result, parsed = await _async_llm_call(
                prompt=prompt, max_tokens=8000, tier="fast",
                operation="discovery_v2_extraction", label=f"v2_phase3_{domain.get('name', '?')}",
                model_config=model_config,
            )
            parsed = _normalize_v2_extraction_result(parsed)
            parsed = _drop_hidden_v2_nodes(parsed, hidden_terms_for_run)
            if not _as_list(parsed.get("processes")):
                logger.info(
                    "v2_phase3_domain_empty_after_hidden_filter domain=%s",
                    domain.get("name", "?"),
                )
                parsed["domain"] = domain
                return parsed
            issues = _v2_extraction_contract_issues(parsed)
            if issues:
                repair_prompt = PromptParts(
                    system=prompt.system,
                    context=prompt.context,
                    variable=(
                        f"{prompt.variable}\n\n"
                        "## Repair required before final answer\n"
                        "Your previous extraction failed Arcflare's process-shape contract:\n"
                        + "\n".join(f"- {issue}" for issue in issues[:12])
                        + "\nReturn the full corrected JSON object. Do not omit child steps, citations, actors, triggers, or touchpoints."
                    ),
                )
                logger.warning(
                    "v2_phase3_contract_retry domain=%s issues=%s",
                    domain.get("name", "?"),
                    issues,
                )
                result, parsed = await _async_llm_call(
                    prompt=repair_prompt, max_tokens=10000, tier="fast",
                    operation="discovery_v2_extraction", label=f"v2_phase3_repair_{domain.get('name', '?')}",
                    model_config=model_config,
                )
                parsed = _normalize_v2_extraction_result(parsed)
                parsed = _drop_hidden_v2_nodes(parsed, hidden_terms_for_run)
                if not _as_list(parsed.get("processes")):
                    logger.info(
                        "v2_phase3_repair_empty_after_hidden_filter domain=%s",
                        domain.get("name", "?"),
                    )
                    parsed["domain"] = domain
                    return parsed
                issues = _v2_extraction_contract_issues(parsed)
                if issues:
                    raise ValueError(
                        f"v2 extraction contract failed for domain '{domain.get('name', '?')}': "
                        + "; ".join(issues[:12])
                    )
            logger.info(
                "v2_phase3_domain_done domain=%s processes=%d tokens_in=%d tokens_out=%d",
                domain.get("name", "?"),
                len(parsed.get("processes", [])),
                result.input_tokens, result.output_tokens,
            )
            parsed["domain"] = domain
            return parsed

    logger.info("v2_phase3_concurrency domains=%d concurrency=%d", len(domains), limit)
    tasks = [_extract_domain(d, b) for d, b in zip(domains, bundles)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    extraction_results: list[dict] = []
    failures: list[str] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("v2_phase3_failed domain=%s error=%s", domains[i].get("name"), r)
            failures.append(f"{domains[i].get('name', '?')}: {r}")
        else:
            extraction_results.append(r)

        if progress_cb:
            progress_cb("extraction", "running", i + 1, len(domains))

    if failures:
        raise RuntimeError("v2 extraction failed quality gates: " + " | ".join(failures[:5]))

    if progress_cb:
        progress_cb("extraction", "done", len(domains), len(domains))

    return extraction_results


async def run_v2_phase4(
    org_id: UUID,
    db: AsyncSession,
    extraction_results: list[dict],
    bundles: list,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
    concurrency: int = 8,
) -> list[dict]:
    """v2 Phase 4: Evidence verification in parallel. Returns updated extraction results."""
    from app.services.processes.evidence import (
        apply_verification_results,
        build_verification_pairs,
    )
    from app.services.processes.prompts import build_v2_phase4_prompt

    if progress_cb:
        progress_cb("verification", "running", 0, len(extraction_results))

    limit = max(1, int(concurrency or 1))
    semaphore = asyncio.Semaphore(limit)
    prompt_lock = asyncio.Lock()

    async def _verify_domain(extraction: dict, bundle) -> dict:
        async with semaphore:
            pairs = build_verification_pairs(bundle, extraction)
            if not pairs:
                return extraction

            async with prompt_lock:
                prompt = await build_v2_phase4_prompt(org_id, db, pairs)
            result, parsed = await _async_llm_call(
                prompt=prompt, max_tokens=6000, tier="fast",
                operation="discovery_v2_verification",
                label=f"v2_phase4_{extraction.get('domain', {}).get('name', '?')}",
                model_config=model_config,
            )

            verifications = parsed.get("verifications", [])
            if verifications:
                updated, ref_verdicts = apply_verification_results(extraction, verifications)
                updated["_ref_verdicts"] = ref_verdicts
                logger.info(
                    "v2_phase4_domain_done domain=%s verified=%d tokens_in=%d tokens_out=%d",
                    extraction.get("domain", {}).get("name", "?"),
                    len(verifications),
                    result.input_tokens, result.output_tokens,
                )
                return updated

            logger.warning(
                "v2_phase4_no_verifications domain=%s",
                extraction.get("domain", {}).get("name", "?"),
            )
            return extraction

    logger.info(
        "v2_phase4_concurrency domains=%d concurrency=%d",
        len(extraction_results),
        limit,
    )
    tasks = [_verify_domain(e, b) for e, b in zip(extraction_results, bundles)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    verified: list[dict] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(
                "v2_phase4_failed domain=%s error=%s",
                extraction_results[i].get("domain", {}).get("name"), r,
            )
            verified.append(extraction_results[i])
        else:
            verified.append(r)

        if progress_cb:
            progress_cb("verification", "running", i + 1, len(extraction_results))

    if progress_cb:
        progress_cb("verification", "done", len(extraction_results), len(extraction_results))

    return verified


async def run_v2_persist(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    verified_results: list[dict],
    bundles: list,
) -> int:
    """Persist v2 extraction results into BusinessProcess and ProcessHandoff rows.

    Returns total process rows created.
    """
    from app.services.processes.evidence import resolve_evidence_refs

    domains_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level == "domain",
        )
    )
    domain_rows = {p.name: p for p in domains_q.scalars().all()}
    total_created = 0

    for extraction, bundle in zip(verified_results, bundles):
        domain_name = extraction.get("domain", {}).get("name", "")
        domain_row = domain_rows.get(domain_name)
        if not domain_row:
            continue

        ref_verdicts = extraction.pop("_ref_verdicts", None)

        for proc in extraction.get("processes", []):
            evidence = resolve_evidence_refs(
                bundle, proc.get("evidence_refs", []),
                verifications=ref_verdicts,
            )
            confidence = float(proc.get("confidence", 0.5))

            proc_row = BusinessProcess(
                org_id=org_id,
                name=str(proc.get("name", "Unnamed"))[:255],
                description=proc.get("description"),
                narrative=proc.get("narrative"),
                level="process",
                parent_id=domain_row.id,
                confidence_score=confidence,
                needs_review=proc.get("needs_review", confidence < NEEDS_REVIEW_CONFIDENCE),
                status="discovered",
                source="discovery",
                discovery_run_id=run_id,
                actors=_as_list(proc.get("actors")),
                trigger_conditions=_as_list(proc.get("trigger_conditions")),
                system_touchpoints=_as_list(proc.get("system_touchpoints")),
                decision_logic=_as_list(proc.get("decision_logic")),
                success_criteria=_as_list(proc.get("success_criteria")),
                failure_modes=_as_list(proc.get("failure_modes")),
                value_classification=proc.get("value_classification"),
                complexity_score=proc.get("complexity_score"),
                automation_potential=proc.get("automation_potential"),
                evidence_sources=evidence,
                metadata_json={},
            )
            db.add(proc_row)
            await db.flush()
            total_created += 1

            for child in proc.get("children", []):
                child_evidence = resolve_evidence_refs(
                    bundle, child.get("evidence_refs", []),
                    verifications=ref_verdicts,
                )
                child_confidence = float(child.get("confidence", 0.5))
                child_row = BusinessProcess(
                    org_id=org_id,
                    name=str(child.get("name", "Unnamed"))[:255],
                    description=child.get("description"),
                    level=child.get("level", "step"),
                    parent_id=proc_row.id,
                    confidence_score=child_confidence,
                    needs_review=child.get("needs_review", child_confidence < NEEDS_REVIEW_CONFIDENCE),
                    status="discovered",
                    source="discovery",
                    discovery_run_id=run_id,
                    actors=_as_list(child.get("actors")),
                    trigger_conditions=_as_list(child.get("trigger_conditions")),
                    system_touchpoints=_as_list(child.get("system_touchpoints")),
                    decision_logic=_as_list(child.get("decision_logic")),
                    success_criteria=_as_list(child.get("success_criteria")),
                    failure_modes=_as_list(child.get("failure_modes")),
                    value_classification=child.get("value_classification"),
                    complexity_score=child.get("complexity_score"),
                    automation_potential=child.get("automation_potential"),
                    estimated_duration=child.get("estimated_duration"),
                    estimated_frequency=child.get("estimated_frequency"),
                    evidence_sources=child_evidence,
                    sequencing=child.get("sequencing", {}),
                    metadata_json={},
                )
                db.add(child_row)
                total_created += 1

        for handoff in extraction.get("intra_domain_handoffs", []):
            source_name = handoff.get("source", "")
            target_name = handoff.get("target", "")
            await db.flush()

            src_q = await db.execute(
                select(BusinessProcess.id).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.name == source_name,
                ).limit(1)
            )
            tgt_q = await db.execute(
                select(BusinessProcess.id).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.name == target_name,
                ).limit(1)
            )
            src_row = src_q.scalar_one_or_none()
            tgt_row = tgt_q.scalar_one_or_none()
            if src_row and tgt_row:
                h_evidence = resolve_evidence_refs(
                    bundle, handoff.get("evidence_refs", []),
                    verifications=ref_verdicts,
                )
                db.add(ProcessHandoff(
                    org_id=org_id,
                    source_process_id=src_row,
                    target_process_id=tgt_row,
                    handoff_type=handoff.get("type", "unknown"),
                    description=handoff.get("description"),
                    confidence_score=float(handoff.get("confidence", 0.5)),
                    discovery_run_id=run_id,
                    evidence_sources=h_evidence,
                ))

    await db.flush()
    return total_created


async def run_v2_phase5(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
    org_ctx: dict,
    verified_results: list[dict],
    bundles: list,
    progress_cb: ProgressCallback = None,
    model_config: dict | None = None,
) -> dict:
    """v2 Phase 5: Cross-domain synthesis. Returns synthesis dict."""
    from app.services.processes.evidence import resolve_evidence_refs
    from app.services.processes.prompts import build_v2_phase5_prompt

    if progress_cb:
        progress_cb("cross_domain_synthesis", "gathering", 0, 1)

    domain_summaries = []
    all_claimed_objects: set[str] = set()
    all_claimed_autos: set[str] = set()

    for extraction, bundle in zip(verified_results, bundles):
        domain = extraction.get("domain", {})
        procs_summary = []
        for proc in extraction.get("processes", []):
            evidence = resolve_evidence_refs(bundle, proc.get("evidence_refs", []))
            procs_summary.append({
                "name": proc.get("name", ""),
                "confidence": proc.get("confidence", 0),
                "evidence_sources": evidence,
            })
            for e in evidence:
                if e.get("type") == "metadata_object":
                    all_claimed_objects.add(e.get("api_name", ""))
                elif e.get("type") == "automation":
                    all_claimed_autos.add(e.get("api_name", ""))

        domain_summaries.append({
            "domain_name": domain.get("name", ""),
            "processes": procs_summary,
        })

    all_obj_q = await db.execute(
        select(MetadataObject.api_name).where(
            MetadataObject.org_id == org_id,
            MetadataObject.record_count > 0,
        )
    )
    all_org_objects = {r[0] for r in all_obj_q.all()}
    orphaned_objects = list(all_org_objects - all_claimed_objects)[:30]

    all_auto_q = await db.execute(
        select(MetadataAutomation.api_name).where(
            MetadataAutomation.org_id == org_id,
        )
    )
    all_org_autos = {r[0] for r in all_auto_q.all()}
    orphaned_autos = list(all_org_autos - all_claimed_autos)[:30]

    cross_edges = await _find_cross_domain_edges(org_id, db, verified_results)

    prompt = await build_v2_phase5_prompt(
        org_id, db, org_ctx, domain_summaries,
        cross_edges, orphaned_objects, orphaned_autos,
    )

    result, parsed = await _async_llm_call(
        prompt=prompt, max_tokens=6000, tier="fast",
        operation="discovery_v2_synthesis", label="v2_phase5",
        model_config=model_config,
    )

    logger.info(
        "v2_phase5_complete org_id=%s handoffs=%d tokens_in=%d tokens_out=%d",
        org_id,
        len(parsed.get("cross_domain_handoffs", [])),
        result.input_tokens, result.output_tokens,
    )

    for handoff in parsed.get("cross_domain_handoffs", []):
        src_name = handoff.get("source_process", "")
        tgt_name = handoff.get("target_process", "")
        src_q = await db.execute(
            select(BusinessProcess.id).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.name == src_name,
            ).limit(1)
        )
        tgt_q = await db.execute(
            select(BusinessProcess.id).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.discovery_run_id == run_id,
                BusinessProcess.name == tgt_name,
            ).limit(1)
        )
        src_id = src_q.scalar_one_or_none()
        tgt_id = tgt_q.scalar_one_or_none()
        if src_id and tgt_id:
            db.add(ProcessHandoff(
                org_id=org_id,
                source_process_id=src_id,
                target_process_id=tgt_id,
                handoff_type=handoff.get("type", "unknown"),
                description=handoff.get("description"),
                confidence_score=float(handoff.get("confidence", 0.5)),
                is_gap=handoff.get("is_gap", False),
                discovery_run_id=run_id,
            ))

    for dn in parsed.get("domain_narratives", []):
        dname = dn.get("domain", "")
        narrative = dn.get("narrative", "")
        if dname and narrative:
            dq = await db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.org_id == org_id,
                    BusinessProcess.discovery_run_id == run_id,
                    BusinessProcess.level == "domain",
                    BusinessProcess.name == dname,
                ).limit(1)
            )
            domain_row = dq.scalar_one_or_none()
            if domain_row:
                domain_row.narrative = narrative

    await db.flush()

    if progress_cb:
        progress_cb("cross_domain_synthesis", "done", 1, 1)

    return parsed


async def _find_cross_domain_edges(
    org_id: UUID,
    db: AsyncSession,
    verified_results: list[dict],
) -> list[dict]:
    """Find MetadataDependency edges that bridge two different domains."""
    domain_objects: dict[str, set[str]] = {}
    for extraction in verified_results:
        dname = extraction.get("domain", {}).get("name", "")
        objs = set(extraction.get("domain", {}).get("key_objects", []))
        domain_objects[dname] = objs

    all_objects: set[str] = set()
    for s in domain_objects.values():
        all_objects.update(s)

    if not all_objects:
        return []

    edges_q = await db.execute(
        select(MetadataDependency).where(
            MetadataDependency.org_id == org_id,
            or_(
                MetadataDependency.source_api_name.in_(all_objects),
                MetadataDependency.target_api_name.in_(all_objects),
            ),
        ).limit(200)
    )

    cross: list[dict] = []
    for e in edges_q.scalars().all():
        src_domain = None
        tgt_domain = None
        for dname, objs in domain_objects.items():
            if e.source_api_name in objs:
                src_domain = dname
            if e.target_api_name in objs:
                tgt_domain = dname
        if src_domain and tgt_domain and src_domain != tgt_domain:
            cross.append({
                "source": e.source_api_name,
                "source_domain": src_domain,
                "target": e.target_api_name,
                "target_domain": tgt_domain,
                "relationship": e.relationship_type,
            })

    return cross


async def run_v2_quality_scoring(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
) -> dict:
    """v2 Phase 6: Quality scoring using evidence_sources instead of v1 touchpoints."""
    all_procs_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level.in_(["process", "subprocess", "step"]),
            BusinessProcess.status != "rejected",
        )
    )
    all_procs = all_procs_q.scalars().all()

    objects_q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.record_count > 0,
            metadata_object_visible_clause(),
        )
    )
    all_objects = objects_q.scalars().all()
    all_object_names = {o.api_name for o in all_objects}

    autos_q = await db.execute(
        select(MetadataAutomation).where(MetadataAutomation.org_id == org_id)
    )
    all_auto_names = {a.api_name for a in autos_q.scalars().all()}
    total_artifacts = len(all_object_names) + len(all_auto_names)

    referenced_objects: set[str] = set()
    referenced_autos: set[str] = set()
    for p in all_procs:
        for ev in (p.evidence_sources or []):
            if not isinstance(ev, dict):
                continue
            etype = ev.get("type", "")
            api = ev.get("api_name", "")
            if etype == "metadata_object" and api:
                referenced_objects.add(api)
            elif etype == "automation" and api:
                referenced_autos.add(api)

    covered = len(referenced_objects & all_object_names) + len(referenced_autos & all_auto_names)
    metadata_coverage = covered / total_artifacts if total_artifacts > 0 else 0.0

    with_evidence = sum(1 for p in all_procs if p.evidence_sources) if all_procs else 0
    evidence_coverage = with_evidence / len(all_procs) if all_procs else 0.0

    with_desc = sum(
        1 for p in all_procs
        if p.description and len(p.description) >= 20
    )
    description_quality = with_desc / len(all_procs) if all_procs else 0.0

    with_value = sum(1 for p in all_procs if p.value_classification)
    value_coverage = with_value / len(all_procs) if all_procs else 0.0

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
        )
    )
    domains = domains_q.scalars().all()
    id_to_proc = {p.id: p for p in all_procs}
    id_to_proc.update({d.id: d for d in domains})

    depths_per_domain: list[int] = []
    if len(domains) > 1:
        for dom in domains:
            max_d = 0
            for p in all_procs:
                current = p
                under = False
                while current:
                    if current.id == dom.id:
                        under = True
                        break
                    current = id_to_proc.get(current.parent_id)
                if under:
                    d = 0
                    c = p
                    while c and c.parent_id:
                        d += 1
                        c = id_to_proc.get(c.parent_id)
                    max_d = max(max_d, d)
            depths_per_domain.append(max_d)

    if len(depths_per_domain) > 1:
        mean_d = statistics.mean(depths_per_domain)
        std_d = statistics.stdev(depths_per_domain)
        hierarchy_consistency = max(0.0, 1.0 - (std_d / mean_d if mean_d > 0 else 0.0))
    else:
        hierarchy_consistency = 1.0

    overall = (
        metadata_coverage * 0.15 +
        evidence_coverage * 0.25 +
        handoff_grounding * 0.15 +
        hierarchy_consistency * 0.10 +
        value_coverage * 0.10 +
        description_quality * 0.15 +
        (1.0 if len(domains) >= 2 else 0.5) * 0.10
    )

    quality_scores = {
        "metadata_coverage": round(metadata_coverage, 3),
        "evidence_coverage": round(evidence_coverage, 3),
        "handoff_grounding": round(handoff_grounding, 3),
        "hierarchy_consistency": round(hierarchy_consistency, 3),
        "value_coverage": round(value_coverage, 3),
        "description_quality": round(description_quality, 3),
        "overall": round(overall, 3),
    }

    run = await db.get(DiscoveryRun, run_id)
    if run:
        run.quality_scores = quality_scores
    await db.flush()

    logger.info("v2_quality_complete org_id=%s run_id=%s scores=%s", org_id, run_id, quality_scores)

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
