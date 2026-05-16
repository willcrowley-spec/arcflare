"""Phase 2: LLM-driven agent opportunity analysis per domain."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)


def validate_opportunity(opp: dict) -> bool:
    if not (opp.get("agent_name") or opp.get("candidate_name") or opp.get("title") or "").strip():
        return False
    if not opp.get("topics"):
        return False
    if not opp.get("replaces"):
        return False
    return True


def _normalize_portfolio_candidate(candidate: dict) -> dict:
    candidate = dict(candidate)
    name = candidate.get("agent_name") or candidate.get("candidate_name") or candidate.get("title")
    candidate["agent_name"] = name
    candidate["portfolio_category_v1"] = candidate.get("portfolio_category") or candidate.get("category")
    candidate["recommended_build_path"] = candidate.get("recommended_build_path") or candidate.get("automation_path")
    if "runtime_reasoning_required" in candidate and "requires_runtime_reasoning" not in candidate:
        candidate["requires_runtime_reasoning"] = candidate["runtime_reasoning_required"]
    return candidate


def parse_opportunity_response(raw: dict | list) -> dict:
    if isinstance(raw, list):
        raw = {"agent_opportunities": raw, "uncovered_processes": []}
    opportunities = (
        raw.get("portfolio_candidates")
        or raw.get("portfolio_candidates_v1")
        or raw.get("agent_opportunities")
        or raw.get("opportunities")
        or []
    )
    uncovered = raw.get("uncovered_processes") or []
    valid = [
        _normalize_portfolio_candidate(o)
        for o in opportunities
        if isinstance(o, dict) and validate_opportunity(o)
    ]
    return {"agent_opportunities": valid, "uncovered_processes": uncovered}


def resolve_ids(opportunity: dict, domain_context: dict) -> dict:
    proc_name_to_id: dict[str, str] = {}
    proc_step_map: dict[str, dict[str, str]] = {}

    for proc in domain_context.get("processes", []):
        pid = proc.get("id", "")
        pname = proc.get("name", "")
        proc_name_to_id[pname.lower()] = pid
        step_map: dict[str, str] = {}
        for step in proc.get("steps", []):
            sname = step.get("name", "")
            sid = step.get("id", "")
            step_map[sname.lower()] = sid
        proc_step_map[pid] = step_map

    for rep in opportunity.get("replaces", []):
        pname = (rep.get("process_name") or "").lower()
        if pname in proc_name_to_id:
            rep["process_id"] = proc_name_to_id[pname]

        pid = rep.get("process_id", "")
        steps = proc_step_map.get(pid, {})
        resolved_step_ids = []
        for sname in rep.get("steps_replaced", []):
            sid = steps.get(sname.lower())
            if sid:
                resolved_step_ids.append(sid)
        rep["step_ids"] = resolved_step_ids

    return opportunity


def _build_prompt(domain_context_json: str, blocks: dict[str, str]) -> str:
    instructions = blocks.get("instructions", "")
    protocol = blocks.get("protocol", "")
    return f"{instructions}\n\n## Domain Context\n\n{domain_context_json}\n\n{protocol}"


async def analyze_domain(
    domain_context: dict,
    org_id: UUID,
    db: AsyncSession,
    *,
    cancel_check: Callable | None = None,
    heartbeat: Callable | None = None,
    prompt_blocks: dict[str, str] | None = None,
) -> dict:
    """Run Phase 2 agent opportunity analysis for a single domain."""
    from app.services.ai.router import llm_call, parse_json_response

    blocks = prompt_blocks or await resolve_prompt_blocks("agent_opportunity", org_id, db)

    ctx_for_llm = {k: v for k, v in domain_context.items() if not k.startswith("_")}
    domain_json = json.dumps(ctx_for_llm, indent=2, default=str)

    prompt = _build_prompt(domain_json, blocks)

    if cancel_check:
        await cancel_check()

    try:
        result = await asyncio.to_thread(
            llm_call,
            prompt=prompt,
            max_tokens=16000,
            tier="strong",
            operation="agent_opportunity",
        )
        data = parse_json_response(result.text)
    except Exception:
        logger.exception(
            "agent_analysis_failed domain=%s org=%s",
            domain_context.get("domain", {}).get("name"),
            org_id,
        )
        return {"agent_opportunities": [], "uncovered_processes": []}

    if heartbeat:
        await heartbeat()

    parsed = parse_opportunity_response(data)

    for opp in parsed["agent_opportunities"]:
        resolve_ids(opp, domain_context)

    return parsed
