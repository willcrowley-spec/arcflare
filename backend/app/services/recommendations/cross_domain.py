"""Phase 3: Cross-domain agent opportunity synthesis."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import ProcessHandoff
from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)


def _summarize_opportunities(all_domain_results: list[dict]) -> list[dict]:
    summaries = []
    for domain_result in all_domain_results:
        domain_name = domain_result.get("_domain_name", "Unknown")
        for opp in domain_result.get("agent_opportunities", []):
            summaries.append({
                "domain": domain_name,
                "agent_name": opp.get("agent_name"),
                "agent_type": opp.get("agent_type"),
                "description": opp.get("description"),
                "topics": [t.get("topic_name") for t in opp.get("topics", [])],
                "actors_impacted": (opp.get("financial_signals") or {}).get("actors_impacted", []),
                "data_requirements": opp.get("data_requirements", []),
                "integration_points": opp.get("integration_points", []),
            })
    return summaries


async def synthesize_cross_domain(
    all_domain_results: list[dict],
    org_id: UUID,
    discovery_run_id: UUID,
    db: AsyncSession,
) -> dict:
    """Run Phase 3: identify cross-domain agent opportunities."""
    if len(all_domain_results) < 2:
        return {"cross_domain_opportunities": [], "merge_suggestions": []}

    from app.services.ai.router import llm_call, parse_json_response

    summaries = _summarize_opportunities(all_domain_results)
    if not summaries:
        return {"cross_domain_opportunities": [], "merge_suggestions": []}

    ho_res = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == discovery_run_id,
        )
    )
    all_handoffs = ho_res.scalars().all()
    cross_domain_handoffs = []
    domain_proc_ids: dict[str, set[str]] = {}
    for dr in all_domain_results:
        dname = dr.get("_domain_name", "")
        ids = set()
        for p in dr.get("_processes_raw", []):
            ids.add(str(p.get("id", "")))
        domain_proc_ids[dname] = ids

    all_domain_ids = set()
    for ids in domain_proc_ids.values():
        all_domain_ids |= ids

    for h in all_handoffs:
        src = str(h.source_process_id)
        tgt = str(h.target_process_id)
        src_domain = None
        tgt_domain = None
        for dname, ids in domain_proc_ids.items():
            if src in ids:
                src_domain = dname
            if tgt in ids:
                tgt_domain = dname
        if src_domain and tgt_domain and src_domain != tgt_domain:
            cross_domain_handoffs.append({
                "source_domain": src_domain,
                "target_domain": tgt_domain,
                "description": h.description,
                "is_gap": h.is_gap,
                "handoff_type": h.handoff_type,
            })

    blocks = await resolve_prompt_blocks("agent_opportunity_cross_domain", org_id, db)
    instructions = blocks.get("instructions", "")
    protocol = blocks.get("protocol", "")

    prompt = (
        f"{instructions}\n\n"
        f"## Agent Opportunities by Domain\n\n"
        f"{json.dumps(summaries, indent=2, default=str)}\n\n"
        f"## Cross-Domain Handoffs\n\n"
        f"{json.dumps(cross_domain_handoffs, indent=2, default=str)}\n\n"
        f"{protocol}"
    )

    try:
        result = llm_call(
            prompt=prompt,
            max_tokens=16000,
            tier="strong",
            operation="agent_opportunity_cross_domain",
        )
        data = parse_json_response(result.text)
    except Exception:
        logger.exception("cross_domain_synthesis_failed org=%s", org_id)
        return {"cross_domain_opportunities": [], "merge_suggestions": []}

    if isinstance(data, list):
        data = {"cross_domain_opportunities": data, "merge_suggestions": []}

    return {
        "cross_domain_opportunities": data.get("cross_domain_opportunities") or [],
        "merge_suggestions": data.get("merge_suggestions") or [],
    }
