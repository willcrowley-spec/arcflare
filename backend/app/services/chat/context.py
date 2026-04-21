"""Assemble LLM-ready chat context (system layers, anchor, history, RAG)."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import langfuse_span
from app.models.chat import ChatMessage, ChatThread
from app.models.discovery import ProcessHandoff
from app.models.organization import Organization
from app.models.process import BusinessProcess
from app.models.recommendation import Recommendation
from app.services.chat.tools import get_tool_declarations
from app.services.documents.vectorizer import search_documents
from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)

def _interpolate_examples_block(text: str, agent_name: str) -> str:
    """Substitute {agent_name}; str.format is unsafe here because examples embed JSON `{"type": ...}`."""
    return text.replace("{agent_name}", agent_name)


async def build_system_prompt(
    org: Organization,
    tool_names: list[str],
    db: AsyncSession,
    *,
    anchor_type: str | None = None,
) -> str:
    """Arc system prompt: identity, rules, protocol, workflow, examples + tools/settings (from prompt store or fallback)."""
    from app.core.config import get_settings

    settings = get_settings()
    agent_name = settings.ARC_AGENT_NAME

    org_settings = org.settings_json or {}
    settings_blob = json.dumps(org_settings, indent=2) if org_settings else "{}"

    decls = get_tool_declarations(anchor_type)
    if tool_names:
        decls = [d for d in decls if d["name"] in tool_names]
    tools_lines = [f"- {d['name']}: {d['description']}" for d in decls]
    tools_block = "\n".join(tools_lines) if tools_lines else "(no tools)"

    blocks = await resolve_prompt_blocks("chat", org.id, db)
    identity = (blocks.get("identity") or "").format(agent_name=agent_name)
    rules = blocks.get("rules") or ""
    protocol = blocks.get("protocol") or ""
    workflow = blocks.get("workflow") or ""
    examples = _interpolate_examples_block(blocks.get("examples") or "", agent_name)

    if anchor_type == "recommendation":
        rec_blocks = await resolve_prompt_blocks("chat_recommendation", org.id, db)
        identity = (rec_blocks.get("identity") or "").format(agent_name=agent_name)
        rules = rec_blocks.get("rules") or ""

    return "\n\n".join([
        identity,
        rules,
        protocol,
        workflow,
        examples,
        f"Available platform tools:\n{tools_block}",
        f"Organization settings:\n{settings_blob}",
    ])


async def _resolve_enrichment_persona(org_id: UUID, db: AsyncSession) -> str:
    blocks = await resolve_prompt_blocks("chat_recommendation", org_id, db)
    return blocks.get("persona") or ""


async def _anchor_context(
    thread: ChatThread,
    db: AsyncSession,
    org_id: UUID,
) -> dict | None:
    if not thread.anchor_type or thread.anchor_id is None:
        return None
    at = thread.anchor_type
    aid = thread.anchor_id
    if at == "gap":
        row = await db.get(ProcessHandoff, aid)
        if row is None or row.org_id != org_id:
            return {"anchor_type": at, "anchor_id": str(aid), "error": "Handoff not found"}
        src = await db.get(BusinessProcess, row.source_process_id)
        tgt = await db.get(BusinessProcess, row.target_process_id)

        def _process_blob(proc: BusinessProcess | None) -> dict | None:
            if proc is None:
                return None
            blob: dict = {
                "id": str(proc.id),
                "name": proc.name,
                "level": proc.level,
                "category": proc.category,
                "status": proc.status,
                "description": proc.description,
                "narrative": proc.narrative,
            }
            if proc.actors:
                blob["actors"] = proc.actors
            if proc.artifacts:
                blob["artifacts"] = proc.artifacts
            return blob

        src_domain = None
        tgt_domain = None
        if src and src.parent_id:
            src_parent = await db.get(BusinessProcess, src.parent_id)
            if src_parent:
                src_domain = {"name": src_parent.name, "level": src_parent.level}
        if tgt and tgt.parent_id:
            tgt_parent = await db.get(BusinessProcess, tgt.parent_id)
            if tgt_parent:
                tgt_domain = {"name": tgt_parent.name, "level": tgt_parent.level}

        return {
            "anchor_type": at,
            "anchor_id": str(aid),
            "handoff": {
                "id": str(row.id),
                "handoff_type": row.handoff_type,
                "description": row.description,
                "confidence_score": row.confidence_score,
                "is_gap": row.is_gap,
                "needs_review": row.needs_review,
                "gap_status": row.gap_status,
                "resolution_note": row.resolution_note,
            },
            "source_process": _process_blob(src),
            "target_process": _process_blob(tgt),
            "source_domain": src_domain,
            "target_domain": tgt_domain,
        }
    if at in ("process", "domain"):
        proc = await db.get(BusinessProcess, aid)
        if proc is None or proc.org_id != org_id:
            return {"anchor_type": at, "anchor_id": str(aid), "error": "Process not found"}
        payload = {
            "id": str(proc.id),
            "name": proc.name,
            "level": proc.level,
            "status": proc.status,
            "category": proc.category,
            "description": proc.description,
            "narrative": proc.narrative,
        }
        if at == "domain" and proc.level != "domain":
            payload["note"] = "Anchor type is domain but record level is not domain; still showing process."
        return {"anchor_type": at, "anchor_id": str(aid), "process": payload}
    if at == "recommendation":
        rec = await db.get(Recommendation, aid)
        if rec is None or rec.org_id != org_id:
            return {"anchor_type": at, "anchor_id": str(aid), "error": "Recommendation not found"}

        assumptions = dict(rec.assumptions_json) if rec.assumptions_json else {}
        overrides = assumptions.get("overrides") if isinstance(assumptions.get("overrides"), dict) else {}
        skip = frozenset({"overrides", "source"})
        base_keys = [k for k in assumptions if k not in skip]
        overridden_keys = sorted(overrides.keys()) if overrides else []
        auto_estimated_keys = sorted(k for k in base_keys if k not in overrides)

        scenarios = dict(rec.scenarios_json) if rec.scenarios_json else {}
        exp = scenarios.get("expected") or {}
        hard = exp.get("hard_savings") or []
        soft = exp.get("soft_savings") or []
        hard_soft = {
            "hard_savings_total_5y": sum(hard) if isinstance(hard, list) else None,
            "soft_savings_total_5y": sum(soft) if isinstance(soft, list) else None,
        }
        hpct = assumptions.get("hard_savings_pct")
        if isinstance(hpct, (int, float)):
            hard_soft["hard_savings_pct_assumption"] = hpct
            hard_soft["soft_savings_pct_assumption"] = 1.0 - float(hpct)

        linked_ids = list(rec.linked_process_ids or [])
        processes_out: list[dict] = []
        for pid_raw in linked_ids:
            try:
                pid = UUID(str(pid_raw))
            except (ValueError, TypeError):
                continue
            proc = await db.get(BusinessProcess, pid)
            if proc is None or proc.org_id != org_id:
                continue
            processes_out.append(
                {
                    "id": str(proc.id),
                    "name": proc.name,
                    "level": proc.level,
                    "narrative": proc.narrative,
                    "actors": proc.actors,
                    "automation_potential": proc.automation_potential,
                }
            )

        anchor_payload = {
            "anchor_type": at,
            "anchor_id": str(aid),
            "recommendation": {
                "id": str(rec.id),
                "title": rec.title,
                "narrative": rec.description,
                "scoring": {
                    "base_score": rec.base_score,
                    "llm_score": rec.llm_score,
                    "composite_score": rec.composite_score,
                    "score_divergence_flag": rec.score_divergence_flag,
                },
                "assumptions": assumptions,
                "projections_summary": {
                    "npv": scenarios.get("npv"),
                    "payback_month": scenarios.get("payback_month"),
                    "estimated_roi": float(rec.estimated_roi) if rec.estimated_roi is not None else None,
                },
                "hard_soft_split": hard_soft,
                "assumption_source": assumptions.get("source"),
                "overridden_assumption_keys": overridden_keys,
                "auto_estimated_assumption_keys": auto_estimated_keys,
                "linked_processes": processes_out,
            },
            "_enrichment_persona": await _resolve_enrichment_persona(org_id, db),
        }
        return anchor_payload
    return {"anchor_type": at, "anchor_id": str(aid), "error": "Unknown anchor_type"}


async def build_chat_context(
    thread: ChatThread,
    db: AsyncSession,
    org: Organization,
    user_message: str,
    *,
    exclude_message_id: UUID | None = None,
) -> list[dict]:
    """Build ordered message dicts: system layers, optional summary/history/RAG, then user."""
    out: list[dict] = []

    decls = get_tool_declarations(thread.anchor_type)
    tool_names = [t["name"] for t in decls]
    out.append(
        {
            "role": "system",
            "content": await build_system_prompt(
                org, tool_names, db, anchor_type=thread.anchor_type,
            ),
        }
    )

    anchor = await _anchor_context(thread, db, org.id)
    if anchor is not None:
        persona = anchor.pop("_enrichment_persona", None)
        out.append(
            {
                "role": "system",
                "content": "The user started this conversation from: "
                + json.dumps(anchor, default=str),
            }
        )
        if persona:
            out.append({"role": "system", "content": persona})

    if thread.summary:
        out.append(
            {
                "role": "system",
                "content": f"Previous conversation summary:\n{thread.summary}",
            }
        )

    hist_filters = [ChatMessage.thread_id == thread.id]
    if exclude_message_id is not None:
        hist_filters.append(ChatMessage.id != exclude_message_id)
    hist = await db.execute(
        select(ChatMessage)
        .where(and_(*hist_filters))
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    hist_rows = list(reversed(hist.scalars().all()))
    for m in hist_rows:
        if m.role not in ("user", "assistant", "system"):
            continue
        out.append({"role": m.role, "content": m.content or ""})

    rag_results: list[dict] = []
    with langfuse_span(name="rag_retrieval", metadata={"query": user_message[:500]}):
        try:
            rag_results = await search_documents(
                query=user_message,
                org_id=org.id,
                top_k=5,
                db=db,
            )
        except Exception as e:
            logger.warning("chat_rag_failed thread_id=%s error=%s", thread.id, e)
            rag_results = []

    if rag_results:
        out.append(
            {
                "role": "system",
                "content": "Relevant knowledge base results:\n"
                + json.dumps(rag_results, default=str),
            }
        )

    out.append({"role": "user", "content": user_message})
    return out
