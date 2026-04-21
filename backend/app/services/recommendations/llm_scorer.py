"""LLM-based qualitative scoring and narrative generation for recommendation candidates.

Anti-anchoring: prompts include only process enrichment — never heuristic base_score.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.router import llm_call, parse_json_response
from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)


def _process_name(candidate: dict, fallback_idx: int) -> str:
    n = str(candidate.get("name") or candidate.get("process_name") or candidate.get("title") or "").strip()
    if n:
        return n
    return f"Candidate_{fallback_idx}"


def _domain_key(candidate: dict) -> str:
    for key in ("parent_name", "parent_process_name", "parent_process"):
        v = candidate.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            v = v.get("name")
        s = str(v).strip() if v is not None else ""
        if s:
            return s
    cat = candidate.get("category")
    if cat:
        s = str(cat).strip()
        if s:
            return s
    return "_ungrouped"


def _evidence_summary(evidence_sources: list[Any]) -> dict[str, Any]:
    if not evidence_sources:
        return {"count": 0, "types": []}
    type_keys: list[str] = []
    for e in evidence_sources:
        if not isinstance(e, dict):
            type_keys.append("unknown")
            continue
        t = e.get("type") or e.get("source_type") or e.get("kind") or "unknown"
        type_keys.append(str(t))
    counts = Counter(type_keys)
    types = [{"type": k, "count": v} for k, v in sorted(counts.items())]
    return {"count": len(evidence_sources), "types": types}


def _enrichment_snapshot(candidate: dict, idx: int) -> dict[str, Any]:
    """Fields exposed to the LLM — no base_score or derived heuristic totals."""
    name = _process_name(candidate, idx)
    ev = candidate.get("evidence_sources") or []
    if not isinstance(ev, list):
        ev = []
    return {
        "process_name": name,
        "description": candidate.get("description"),
        "narrative": candidate.get("narrative"),
        "actors": candidate.get("actors") or [],
        "trigger_conditions": candidate.get("trigger_conditions") or [],
        "decision_logic": candidate.get("decision_logic") or [],
        "system_touchpoints": candidate.get("system_touchpoints") or [],
        "failure_modes": candidate.get("failure_modes") or [],
        "evidence_sources": _evidence_summary(ev),
        "value_classification": candidate.get("value_classification"),
        "complexity_score": candidate.get("complexity_score"),
        "automation_type": candidate.get("automation_type"),
        "automation_potential": candidate.get("automation_potential"),
        "estimated_duration": candidate.get("estimated_duration"),
        "estimated_frequency": candidate.get("estimated_frequency"),
        "confidence_score": candidate.get("confidence_score"),
    }


def _batch_by_domain(
    candidates: list[dict],
) -> dict[str, list[tuple[int, dict]]]:
    groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[_domain_key(c)].append((i, c))
    return dict(groups)


def _iter_batches(
    grouped: dict[str, list[tuple[int, dict]]], max_per_batch: int
) -> Iterator[tuple[str, list[tuple[int, dict]]]]:
    for domain, items in grouped.items():
        for start in range(0, len(items), max_per_batch):
            yield domain, items[start : start + max_per_batch]


def _coerce_llm_rows(data: Any) -> list[dict] | None:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("results", "scores", "candidates", "items", "recommendations"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return None


def _build_prompt(snapshots: list[dict[str, Any]], blocks: dict[str, str]) -> str:
    payload = json.dumps(snapshots, indent=2, default=str)
    instructions = blocks.get("instructions", "")
    protocol = blocks.get("protocol", "")
    return f"""{instructions}

Processes (JSON array of enrichment records):
{payload}

{protocol}"""


def _merge_llm_row(candidate: dict, row: dict) -> None:
    """Merge LLM output into *candidate* in place.

    Heuristic-only keys (e.g. ``signals``, ``gate_score``, ``refinement_score``) are not
    read from *row* and are left unchanged on *candidate*.
    """
    raw_score = row.get("llm_score")
    try:
        llm_score = float(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        llm_score = None
    if llm_score is not None:
        llm_score = max(0.0, min(1.0, llm_score))

    candidate["llm_score"] = llm_score
    candidate["llm_rationale"] = row.get("score_rationale")

    executive_summary = row.get("executive_summary")
    if executive_summary is not None:
        candidate["narrative"] = executive_summary

    candidate["llm_analysis"] = {
        "current_state": row.get("current_state"),
        "automation_approach": row.get("automation_approach"),
        "executive_summary": executive_summary,
        "risks": row.get("risks"),
        "automation_type_rationale": row.get("automation_type_rationale"),
    }

    assumptions = row.get("assumptions")
    if isinstance(assumptions, dict):
        candidate["assumptions_json"] = {
            **assumptions,
            "source": "auto_estimated",
            "overrides": {},
        }
    else:
        candidate["assumptions_json"] = {"source": "auto_estimated", "overrides": {}}

    actions = row.get("actions")
    if isinstance(actions, list):
        candidate["actions_json"] = actions
    else:
        candidate["actions_json"] = []

    override = row.get("automation_type_override")
    if override is not None and str(override).strip().lower() not in ("null", "none", ""):
        val = str(override).strip().lower()
        _VALID = {"deterministic", "agentic", "hybrid"}
        if val in _VALID:
            candidate["automation_type"] = val


def _mark_incomplete(candidate: dict) -> None:
    candidate["llm_score"] = None
    candidate["llm_rationale"] = None
    candidate["narrative"] = None
    candidate["assumptions_json"] = {}
    candidate["actions_json"] = []


async def score_candidates_with_llm(
    candidates: list[dict],
    org_id: UUID,
    db: AsyncSession,
    model_config: dict | None = None,
    *,
    max_per_batch: int = 8,
    cancel_check: Callable[[], Awaitable[None]] | None = None,
    heartbeat: Callable[[], Awaitable[None]] | None = None,
) -> list[dict]:
    """Run an LLM scoring pass over candidates; merge results by process_name.

    Candidates without a successful LLM row get llm_score=None and empty LLM fields.

    If *cancel_check* is provided it is awaited before each batch. It should
    raise an exception (e.g. ``PipelineCancelled``) to abort early.

    If *heartbeat* is provided it is awaited after each completed batch so the
    caller can update a liveness timestamp (prevents staleness timeouts on
    long-running scoring runs).
    """
    if not candidates:
        return []

    blocks = await resolve_prompt_blocks("recommendations", org_id, db)

    out = [dict(c) for c in candidates]
    merged_name_per_index: dict[int, str] = {}

    grouped = _batch_by_domain(out)

    for domain, batch in _iter_batches(grouped, max_per_batch):
        if cancel_check is not None:
            await cancel_check()

        snapshots = [_enrichment_snapshot(c, i) for i, c in batch]
        prompt = _build_prompt(snapshots, blocks)
        try:
            result = await asyncio.to_thread(
                lambda p=prompt: llm_call(
                    prompt=p,
                    max_tokens=12000,
                    tier="strong",
                    operation="recommendations",
                    model_config=model_config,
                )
            )
            data = parse_json_response(result.text)
        except Exception:
            logger.exception("llm_scorer_batch_failed domain=%s batch_size=%d", domain, len(batch))
            continue

        rows = _coerce_llm_rows(data)
        if rows is None:
            logger.warning(
                "llm_scorer_malformed_json domain=%s batch_size=%d — skipping batch",
                domain,
                len(batch),
            )
            continue

        by_name: dict[str, dict] = {}
        for row in rows:
            pname = row.get("process_name")
            if pname is not None and str(pname).strip():
                by_name[str(pname).strip()] = row

        for i, c in batch:
            pname = _process_name(c, i)
            row = by_name.get(pname)
            if not row:
                continue
            _merge_llm_row(out[i], row)
            merged_name_per_index[i] = pname

        if heartbeat is not None:
            await heartbeat()

    for i in range(len(out)):
        if i not in merged_name_per_index:
            _mark_incomplete(out[i])

    return out
