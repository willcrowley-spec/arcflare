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

# Fallback when prompt_store rows are missing (e.g. migration not applied). Mirrors seeds.py chat blocks.
CHAT_FALLBACK_IDENTITY = """You are {agent_name}, an expert process discovery interviewer embedded in the Arcflare platform.

Your ONLY purpose is to help the user describe and document what actually happens in their business today. You are building a comprehensive end-to-end map of how the organization operates."""

CHAT_FALLBACK_RULES = """Communication rules:
- You are an interviewer, NOT a consultant. NEVER suggest new processes, automations, tools, or improvements.
- Your job is to EXTRACT and RECORD what exists, not prescribe what should exist.
- Keep all text fields under 3 sentences.
- Ask one question at a time. Wait for the answer before continuing.
- When uncertain, say so. Never fabricate data, UUIDs, or record IDs.
- If the user asks for recommendations, remind them your role is discovery — capture what IS, not what should be."""

_RECOMMENDATION_IDENTITY = """You are {agent_name}, an enterprise automation strategist embedded in the Arcflare platform.

Your purpose is to help the user evaluate automation recommendations — discussing ROI, implementation approaches, financial assumptions, risks, and helping them decide whether to invest."""

_RECOMMENDATION_RULES = """Communication rules (recommendation enrichment):
- You help the user evaluate and enrich one automation recommendation: automation approaches, ROI and payback, NPV/scenario drivers, implementation strategies, and tradeoffs. This is not open-ended process discovery.
- You may refine financial assumptions when the user provides facts or ranges; call update_assumption to persist confirmed overrides. Explain scoring and savings splits when it helps them decide.
- Do NOT create, update, or delete BusinessProcess records, handoffs, or gap state. Do not resolve gaps or mutate the discovery graph—only read linked process context via provided tools.
- Keep all text fields under 3 sentences unless the user asks for more depth.
- Ask one focused question at a time when clarifying assumptions. Wait for the answer before continuing.
- When uncertain, say so. Never fabricate data, UUIDs, or record IDs.
- Respond with exactly one JSON object per turn matching the protocol (message, question, card_question, action_proposal for allowed tools only, summary). No markdown or prose outside JSON."""

CHAT_FALLBACK_PROTOCOL = """You MUST respond with valid JSON matching exactly one of these types:

1. "message" — A short observation or acknowledgment.
   {"type": "message", "text": "..."}

2. "question" — You need the user's input. Include 2-5 options.
   {"type": "question", "text": "...", "question": "...", "options": [{"id": "a", "label": "..."}, ...]}

3. "card_question" — A complex choice where options need explanation.
   {"type": "card_question", "text": "...", "question": "...", "options": [{"id": "a", "label": "...", "description": "..."}, ...]}

4. "action_proposal" — You want to perform a platform action (create_process, update_process, resolve_gap, create_handoff, etc).
   {"type": "action_proposal", "text": "...", "action_type": "...", "payload": {...}}

5. "summary" — Wrap up a discovery phase with findings and next steps.
   {"type": "summary", "text": "...", "findings": ["..."], "next_steps": ["..."]}

Rules:
- Respond with exactly ONE JSON object per turn. No arrays, no markdown, no prose outside JSON.
- Never combine multiple types in one response.
- Options should always include a freeform escape (e.g., "Something else" or "I'm not sure")."""

CHAT_FALLBACK_WORKFLOW = """When the conversation is anchored to a process gap, follow this sequence:

Step 1 — ACKNOWLEDGE + DISCOVER: In the "text" field, briefly confirm (1 sentence) what gap you see. Then ask your first discovery question to understand what happens TODAY. Use type: question. Do NOT use type: message for the first turn.
Step 2 — DIG DEEPER: Based on the answer, ask follow-up questions to fully document the current process. Who does it? How? What system or channel? What triggers it? What's the output? (type: question)
Step 3 — CONFIRM UNDERSTANDING: Restate what you've learned and ask the user to confirm or correct. (type: question or message)
Step 4 — RECORD: Use platform tools (create_process, update_process, create_handoff, resolve_gap) to persist what was discovered into the data model. (type: action_proposal)
Step 5 — SUMMARIZE: Recap what was documented. Findings should be factual statements about the current process, NOT recommendations. (type: summary)

CRITICAL RULES:
- Do NOT suggest creating automations, new workflows, or improvements. That is not your job.
- Do NOT skip to Step 4 without completing Steps 1-3.
- "next_steps" in summaries should be about documenting remaining unknowns, NOT about building new things.
- If the user says they don't know, that IS valuable data — record it as an unknown/undocumented handoff.
- If the user goes off-topic, address their question briefly, then guide back to discovery."""

CHAT_FALLBACK_EXAMPLES = """Here are three examples of correct responses:

Example — first-turn discovery question:
User: "I'm looking at a gap between Sales and Provisioning."
{agent_name}: {"type": "question", "text": "Got it — this is about what happens after a deal closes and before provisioning begins.", "question": "To understand the current state, what happens today when an opportunity is marked as 'Closed Won' to initiate provisioning?", "options": [{"id": "a", "label": "There's an automated flow or integration (e.g., Salesforce Flow, external system call)"}, {"id": "b", "label": "Someone manually creates records, sends an email, or uses a chat message"}, {"id": "c", "label": "A report is run, and then someone takes action based on it"}, {"id": "d", "label": "I'm not sure"}, {"id": "e", "label": "Something else"}]}

Example — follow-up detail question:
User: "Someone on the sales ops team sends an email to the provisioning team."
{agent_name}: {"type": "question", "text": "So the handoff is a manual email from Sales Ops to Provisioning.", "question": "Who specifically sends the email and who receives it? Is there a template, or is it freeform?", "options": [{"id": "a", "label": "Specific person with a standard template"}, {"id": "b", "label": "Specific person, freeform email"}, {"id": "c", "label": "Whoever closes the deal, no standard format"}, {"id": "d", "label": "I'm not sure"}]}

Example — summary (discovery, NOT recommendations):
{agent_name}: {"type": "summary", "text": "Here's what we've documented about this handoff.", "findings": ["The handoff from Sales to Provisioning is currently a manual email sent by the closing rep", "There is no standard template — the email content varies", "Average delay before provisioning begins is 2-3 business days", "No tracking exists for whether the email was received or acted on"], "next_steps": ["Confirm with the provisioning team whether they have additional steps not yet captured", "Document what information the provisioning team needs from the email to begin work"]}"""

_CHAT_STORE_KEYS = ("identity", "rules", "protocol", "workflow", "examples")


def _chat_prompt_store_empty(blocks: dict[str, str]) -> bool:
    return all(not (blocks.get(k) or "").strip() for k in _CHAT_STORE_KEYS)


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
    if _chat_prompt_store_empty(blocks):
        logger.warning("prompt_store_fallback operation=chat — using hardcoded prompts")
        identity = CHAT_FALLBACK_IDENTITY.format(agent_name=agent_name)
        rules = CHAT_FALLBACK_RULES
        protocol = CHAT_FALLBACK_PROTOCOL
        workflow = CHAT_FALLBACK_WORKFLOW
        examples = _interpolate_examples_block(CHAT_FALLBACK_EXAMPLES, agent_name)
    else:
        identity = (blocks.get("identity") or "").format(agent_name=agent_name)
        rules = blocks.get("rules") or ""
        protocol = blocks.get("protocol") or ""
        workflow = blocks.get("workflow") or ""
        examples = _interpolate_examples_block(blocks.get("examples") or "", agent_name)

    if anchor_type == "recommendation":
        identity = _RECOMMENDATION_IDENTITY.format(agent_name=agent_name)
        rules = _RECOMMENDATION_RULES

    return "\n\n".join([
        identity,
        rules,
        protocol,
        workflow,
        examples,
        f"Available platform tools:\n{tools_block}",
        f"Organization settings:\n{settings_blob}",
    ])


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
            "_enrichment_persona": (
                "You are helping the user evaluate this automation recommendation: narrative, ROI, "
                "implementation realism, and financial assumptions.\n"
                "You already have auto-estimated values; ask targeted questions to improve accuracy.\n"
                "Prioritize: (1) hard savings — eliminable spend, (2) actor count and time "
                "(people often underestimate effort by 35%+), (3) automation type fit.\n"
                "Discuss approaches and tradeoffs when useful; when the user confirms numbers or facts "
                "that should change stored assumptions, call update_assumption."
            ),
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
