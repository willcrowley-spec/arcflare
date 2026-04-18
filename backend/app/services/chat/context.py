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
from app.services.chat.tools import get_tool_declarations
from app.services.documents.vectorizer import search_documents

logger = logging.getLogger(__name__)


def build_system_prompt(org: Organization, tool_names: list[str]) -> str:
    """Three-layer Arc system prompt: identity, protocol, workflow + few-shot examples."""
    from app.core.config import get_settings

    settings = get_settings()
    agent_name = settings.ARC_AGENT_NAME

    org_settings = org.settings_json or {}
    settings_blob = json.dumps(org_settings, indent=2) if org_settings else "{}"

    decls = get_tool_declarations()
    if tool_names:
        decls = [d for d in decls if d["name"] in tool_names]
    tools_lines = [f"- {d['name']}: {d['description']}" for d in decls]
    tools_block = "\n".join(tools_lines) if tools_lines else "(no tools)"

    layer1_identity = f"""You are {agent_name}, a senior process analyst embedded in the Arcflare platform.

Communication rules:
- You work WITH the user to resolve process gaps. You do not lecture.
- Keep all text fields under 3 sentences.
- Ask one question at a time. Wait for the answer before continuing.
- Never dump analysis unprompted. Discovery first, action second.
- When uncertain, say so. Never fabricate data, UUIDs, or record IDs."""

    layer2_protocol = """You MUST respond with valid JSON matching exactly one of these types:

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

    layer3_workflow = """When the conversation is anchored to a process gap, follow this sequence:

Step 1 — ACKNOWLEDGE: Confirm what gap you're looking at in one sentence. (type: message)
Step 2 — DISCOVER CURRENT STATE: Ask what happens today. 1-2 questions max. (type: question)
Step 3 — ASSESS IMPACT: Ask about severity, frequency, or business impact. (type: question)
Step 4 — PROPOSE RESOLUTION: Suggest 1-2 specific actions using platform tools. (type: action_proposal or card_question)
Step 5 — SUMMARIZE: Recap findings and agreed next steps. (type: summary)

Do NOT skip to Step 4 without completing Steps 1-3.
If the user goes off-topic, address their question briefly, then guide back to the workflow."""

    few_shot = """Here are two examples of correct responses:

Example — question response:
User: "I'm looking at a gap between Sales and Provisioning."
{agent_name}: {"type": "question", "text": "Got it — this is about how a closed deal triggers customer provisioning.", "question": "Do you know what happens today when an opportunity is closed-won?", "options": [{"id": "a", "label": "There's an automated flow in Salesforce"}, {"id": "b", "label": "Someone manually hands it off"}, {"id": "c", "label": "I'm not sure"}, {"id": "d", "label": "Nothing — it's broken"}]}

Example — summary response:
{agent_name}: {"type": "summary", "text": "Here's what we've established about this gap.", "findings": ["The handoff from Sales to Provisioning is currently manual via email", "Average delay is 2-3 business days", "No tracking exists for dropped handoffs"], "next_steps": ["Create an automated trigger on Closed Won stage", "Add a provisioning request object to track handoffs"]}""".replace("{agent_name}", agent_name)

    return "\n\n".join([
        layer1_identity,
        layer2_protocol,
        layer3_workflow,
        few_shot,
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
        return {
            "anchor_type": at,
            "anchor_id": str(aid),
            "handoff": {
                "id": str(row.id),
                "handoff_type": row.handoff_type,
                "description": row.description,
                "is_gap": row.is_gap,
                "gap_status": row.gap_status,
                "resolution_note": row.resolution_note,
                "source_process_name": src.name if src else None,
                "target_process_name": tgt.name if tgt else None,
            },
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

    tool_names = [t["name"] for t in get_tool_declarations()]
    out.append({"role": "system", "content": build_system_prompt(org, tool_names)})

    anchor = await _anchor_context(thread, db, org.id)
    if anchor is not None:
        out.append(
            {
                "role": "system",
                "content": "The user started this conversation from: "
                + json.dumps(anchor, default=str),
            }
        )

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
