"""Execute chat actions and auto-execute read-only tools."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatAction
from app.models.discovery import ProcessHandoff
from app.models.process import BusinessProcess
from app.services.chat.validation import _collect_descendant_ids
from app.services.documents.vectorizer import search_documents

logger = logging.getLogger(__name__)


def _process_dict(p: BusinessProcess) -> dict:
    return {
        "id": str(p.id),
        "org_id": str(p.org_id),
        "name": p.name,
        "category": p.category,
        "description": p.description,
        "efficiency_score": p.efficiency_score,
        "automation_level": p.automation_level,
        "status": p.status,
        "source": p.source,
        "sub_process_count": p.sub_process_count,
        "managed_asset_count": p.managed_asset_count,
        "metadata_json": p.metadata_json,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "parent_id": str(p.parent_id) if p.parent_id else None,
        "level": p.level,
        "confidence_score": p.confidence_score,
        "needs_review": p.needs_review,
        "narrative": p.narrative,
        "discovery_run_id": str(p.discovery_run_id) if p.discovery_run_id else None,
        "actors": p.actors,
        "artifacts": p.artifacts,
    }


async def execute_auto_tool(
    tool_name: str,
    params: dict,
    org_id: UUID,
    db: AsyncSession,
) -> dict:
    if tool_name == "search_knowledge":
        q = str(params.get("query") or "")
        rows = await search_documents(query=q, org_id=org_id, top_k=8, db=db)
        return {"results": rows, "count": len(rows)}

    if tool_name == "get_process_detail":
        raw = params.get("process_id")
        pid = UUID(str(raw)) if raw else None
        if pid is None:
            return {"ok": False, "error": "process_id is required"}
        proc = await db.get(BusinessProcess, pid)
        if proc is None or proc.org_id != org_id:
            return {"ok": False, "error": "Process not found"}
        ch = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.parent_id == pid,
            )
        )
        children = [_process_dict(c) for c in ch.scalars().all()]
        ho = await db.execute(
            select(ProcessHandoff).where(
                ProcessHandoff.org_id == org_id,
                ProcessHandoff.source_process_id == pid,
            )
        )
        hi = await db.execute(
            select(ProcessHandoff).where(
                ProcessHandoff.org_id == org_id,
                ProcessHandoff.target_process_id == pid,
            )
        )
        return {
            "process": _process_dict(proc),
            "children": children,
            "handoffs_outgoing": [_handoff_summary(h) for h in ho.scalars().all()],
            "handoffs_incoming": [_handoff_summary(h) for h in hi.scalars().all()],
        }

    if tool_name == "list_gaps":
        q = await db.execute(
            select(ProcessHandoff).where(
                ProcessHandoff.org_id == org_id,
                ProcessHandoff.is_gap == True,
            )
        )
        rows = q.scalars().all()
        items = []
        for h in rows:
            items.append(await format_gap_handoff_item(h, db))
        return {"items": items, "total": len(items)}

    return {"ok": False, "error": f"Unknown or non-auto tool: {tool_name}"}


def _handoff_summary(h: ProcessHandoff) -> dict:
    return {
        "id": str(h.id),
        "source_process_id": str(h.source_process_id),
        "target_process_id": str(h.target_process_id),
        "handoff_type": h.handoff_type,
        "description": h.description,
        "confidence_score": h.confidence_score,
        "is_gap": h.is_gap,
        "gap_status": h.gap_status,
    }


async def _parent_name(proc: BusinessProcess | None, db: AsyncSession) -> str | None:
    if proc is None or proc.parent_id is None:
        return None
    parent = await db.get(BusinessProcess, proc.parent_id)
    return parent.name if parent else None


async def format_gap_handoff_item(h: ProcessHandoff, db: AsyncSession) -> dict:
    src = await db.get(BusinessProcess, h.source_process_id)
    tgt = await db.get(BusinessProcess, h.target_process_id)
    return {
        "id": str(h.id),
        "source_process_id": str(h.source_process_id),
        "target_process_id": str(h.target_process_id),
        "source_process_name": src.name if src else None,
        "target_process_name": tgt.name if tgt else None,
        "source_domain_name": await _parent_name(src, db),
        "target_domain_name": await _parent_name(tgt, db),
        "handoff_type": h.handoff_type,
        "description": h.description,
        "confidence_score": h.confidence_score,
        "gap_status": h.gap_status,
        "resolution_note": h.resolution_note,
        "is_gap": h.is_gap,
        "needs_review": h.needs_review,
    }


async def _execute_create_process(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    parent_id = None
    if payload.get("parent_id"):
        parent_id = UUID(str(payload["parent_id"]))
        parent = await db.get(BusinessProcess, parent_id)
        if parent is None or parent.org_id != org_id:
            raise ValueError("parent_id not found in organization")
    row = BusinessProcess(
        org_id=org_id,
        name=str(payload["name"]),
        category=payload.get("category"),
        description=payload.get("description"),
        efficiency_score=None,
        automation_level=None,
        status="draft",
        source="chat_assistant",
        sub_process_count=0,
        managed_asset_count=0,
        metadata_json={},
        parent_id=parent_id,
        level=str(payload.get("level") or "process"),
        confidence_score=None,
        needs_review=False,
        narrative=None,
        discovery_run_id=None,
        actors=payload.get("actors") if isinstance(payload.get("actors"), list) else [],
        artifacts=payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("chat_action_create_process org_id=%s process_id=%s", org_id, row.id)
    return {"id": str(row.id), "name": row.name}


async def _execute_update_process(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    pid = UUID(str(payload["process_id"]))
    proc = await db.get(BusinessProcess, pid)
    if proc is None or proc.org_id != org_id:
        raise ValueError("Process not found")
    allowed = (
        "name",
        "description",
        "status",
        "category",
        "confidence_score",
        "narrative",
        "actors",
        "artifacts",
    )
    updated_fields: list[str] = []
    for key in allowed:
        if key not in payload:
            continue
        val = payload[key]
        setattr(proc, key, val)
        updated_fields.append(key)
    await db.commit()
    await db.refresh(proc)
    logger.info("chat_action_update_process org_id=%s process_id=%s fields=%s", org_id, pid, updated_fields)
    return {"id": str(proc.id), "updated_fields": updated_fields}


async def _execute_delete_process(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    pid = UUID(str(payload["process_id"]))
    proc = await db.get(BusinessProcess, pid)
    if proc is None or proc.org_id != org_id:
        raise ValueError("Process not found")
    descendants = await _collect_descendant_ids(pid, org_id, db)
    n = 0
    for did in descendants:
        p = await db.get(BusinessProcess, did)
        if p and p.org_id == org_id and p.status != "deleted":
            p.status = "deleted"
            n += 1
    await db.commit()
    logger.warning(
        "chat_action_delete_process org_id=%s root_id=%s deleted_rows=%s",
        org_id,
        pid,
        n,
    )
    return {"id": str(pid), "deleted_children": max(0, n - 1)}


async def _execute_create_handoff(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    sid = UUID(str(payload["source_process_id"]))
    tid = UUID(str(payload["target_process_id"]))
    sp = await db.get(BusinessProcess, sid)
    tp = await db.get(BusinessProcess, tid)
    if not sp or not tp or sp.org_id != org_id or tp.org_id != org_id:
        raise ValueError("Source or target process not found in organization")
    row = ProcessHandoff(
        org_id=org_id,
        source_process_id=sid,
        target_process_id=tid,
        handoff_type=str(payload["handoff_type"]),
        description=payload.get("description"),
        confidence_score=float(payload.get("confidence_score", 0.0) or 0.0),
        is_gap=bool(payload.get("is_gap", False)),
        needs_review=bool(payload.get("needs_review", False)),
        discovery_run_id=None,
        metadata_json={},
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("chat_action_create_handoff org_id=%s handoff_id=%s", org_id, row.id)
    return {"id": str(row.id)}


async def _execute_update_handoff(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    hid = UUID(str(payload["handoff_id"]))
    row = await db.get(ProcessHandoff, hid)
    if row is None or row.org_id != org_id:
        raise ValueError("Handoff not found")
    if "handoff_type" in payload and payload["handoff_type"] is not None:
        row.handoff_type = str(payload["handoff_type"])
    if "description" in payload:
        row.description = payload["description"]
    if "confidence_score" in payload and payload["confidence_score"] is not None:
        row.confidence_score = float(payload["confidence_score"])
    await db.commit()
    await db.refresh(row)
    logger.info("chat_action_update_handoff org_id=%s handoff_id=%s", org_id, hid)
    return {"id": str(row.id)}


async def _execute_resolve_gap(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    hid = UUID(str(payload["handoff_id"]))
    row = await db.get(ProcessHandoff, hid)
    if row is None or row.org_id != org_id:
        raise ValueError("Handoff not found")
    row.gap_status = "resolved"
    row.resolution_note = str(payload.get("resolution_note") or "")
    await db.commit()
    await db.refresh(row)
    logger.info("chat_action_resolve_gap org_id=%s handoff_id=%s", org_id, hid)
    return {"id": str(row.id), "status": "resolved"}


async def _execute_rerun_synthesis(payload: dict, db: AsyncSession, org_id: UUID) -> dict:
    from app.workers.process_discovery import process_discovery_task

    _ = payload, db
    process_discovery_task.delay(str(org_id))
    logger.info("chat_action_rerun_synthesis org_id=%s queued=1", org_id)
    return {"status": "queued"}


_ACTION_HANDLERS = {
    "create_process": _execute_create_process,
    "update_process": _execute_update_process,
    "delete_process": _execute_delete_process,
    "create_handoff": _execute_create_handoff,
    "update_handoff": _execute_update_handoff,
    "resolve_gap": _execute_resolve_gap,
    "rerun_synthesis": _execute_rerun_synthesis,
}


async def execute_action(action: ChatAction, db: AsyncSession, org_id: UUID) -> dict:
    fn = _ACTION_HANDLERS.get(action.action_type)
    if fn is None:
        raise ValueError(f"Unsupported action_type: {action.action_type}")
    payload = dict(action.payload or {})
    return await fn(payload, db, org_id)
