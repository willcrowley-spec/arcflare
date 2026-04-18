"""AI chat assistant HTTP API (threads, messages, actions)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentOrg, CurrentUserDep, DbSession
from app.core.security import CurrentUser
from app.models.chat import ChatAction, ChatMessage, ChatThread
from app.models.organization import Organization, User
from app.schemas.chat import (
    ActionConfirm,
    ActionResponse,
    MessageCreate,
    MessageResponse,
    ThreadCreate,
    ThreadDetailResponse,
    ThreadListResponse,
    ThreadResponse,
)
from app.services.chat.actions import execute_action
from app.services.chat.context import build_chat_context
from app.services.ai.router import llm_call

logger = logging.getLogger(__name__)

router = APIRouter()


def _messages_to_prompt(msgs: list[dict]) -> str:
    blocks: list[str] = []
    for m in msgs:
        role = str(m.get("role", "user")).upper()
        content = str(m.get("content", ""))
        blocks.append(f"[{role}]\n{content}")
    return "\n\n".join(blocks)


def _trace_id_from_span(span: object | None) -> str | None:
    if span is None:
        return None
    for attr in ("trace_id", "traceId", "id"):
        tid = getattr(span, attr, None)
        if tid:
            return str(tid)
    return None


async def _get_or_create_user(
    db: DbSession,
    org: Organization,
    current_user: CurrentUser,
) -> User:
    res = await db.execute(
        select(User).where(
            User.clerk_user_id == current_user.clerk_user_id,
            User.org_id == org.id,
        )
    )
    row = res.scalar_one_or_none()
    if row is not None:
        return row
    row = User(
        org_id=org.id,
        clerk_user_id=current_user.clerk_user_id,
        email=current_user.email,
        display_name=None,
        role="member",
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
        logger.info("auto_created_user clerk_user_id=%s org_id=%s", current_user.clerk_user_id, org.id)
        return row
    except Exception as e:
        await db.rollback()
        logger.warning("user_create_failed retry_lookup error=%s", e)
        res2 = await db.execute(
            select(User).where(User.clerk_user_id == current_user.clerk_user_id)
        )
        existing = res2.scalar_one_or_none()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not resolve user record",
            ) from e
        if existing.org_id != org.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not registered for this organization",
            )
        return existing


@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: ThreadCreate,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ChatThread:
    u = await _get_or_create_user(db, org, user)
    thread = ChatThread(
        org_id=org.id,
        user_id=u.id,
        anchor_type=body.anchor_type,
        anchor_id=body.anchor_id,
        model_override=body.model_override,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ThreadListResponse:
    u = await _get_or_create_user(db, org, user)
    q = await db.execute(
        select(ChatThread)
        .where(
            ChatThread.user_id == u.id,
            ChatThread.org_id == org.id,
            ChatThread.status == "active",
        )
        .order_by(ChatThread.updated_at.desc())
    )
    rows = q.scalars().all()
    items = [ThreadResponse.model_validate(r) for r in rows]
    return ThreadListResponse(items=items, total=len(items))


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread_detail(
    thread_id: UUID,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ThreadDetailResponse:
    u = await _get_or_create_user(db, org, user)
    q = await db.execute(
        select(ChatThread)
        .options(
            selectinload(ChatThread.messages),
            selectinload(ChatThread.actions),
        )
        .where(
            ChatThread.id == thread_id,
            ChatThread.org_id == org.id,
            ChatThread.user_id == u.id,
        )
    )
    thread = q.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    msgs = sorted(thread.messages, key=lambda m: m.created_at)[-50:]
    pending = [a for a in thread.actions if a.status == "proposed"]
    return ThreadDetailResponse(
        thread=ThreadResponse.model_validate(thread),
        messages=[MessageResponse.model_validate(m) for m in msgs],
        pending_actions=[ActionResponse.model_validate(a) for a in pending],
    )


@router.delete("/threads/{thread_id}", response_model=ThreadResponse)
async def archive_thread(
    thread_id: UUID,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ChatThread:
    u = await _get_or_create_user(db, org, user)
    q = await db.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.org_id == org.id,
            ChatThread.user_id == u.id,
        )
    )
    thread = q.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.status = "archived"
    await db.commit()
    await db.refresh(thread)
    return thread


@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: UUID,
    body: MessageCreate,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> StreamingResponse:
    from app.core.observability import langfuse_span

    u = await _get_or_create_user(db, org, user)
    q = await db.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.org_id == org.id,
            ChatThread.user_id == u.id,
            ChatThread.status == "active",
        )
    )
    thread = q.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    user_msg = ChatMessage(thread_id=thread.id, role="user", content=body.content)
    db.add(user_msg)
    thread.message_count = int(thread.message_count or 0) + 1
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(thread)

    assistant_text = ""
    token_total: int | None = None
    trace_id: str | None = None

    with langfuse_span(
        name="chat_request",
        session_id=str(thread.id),
        metadata={"user_id": str(u.id), "thread_id": str(thread.id)},
    ) as span:
        try:
            ctx = await build_chat_context(
                thread,
                db,
                org,
                body.content,
                exclude_message_id=user_msg.id,
            )
            full_prompt = _messages_to_prompt(ctx)
            result = llm_call(
                full_prompt,
                max_tokens=4096,
                tier="fast",
                operation="chat",
                model_config=org.analysis_config,
            )
            assistant_text = result.text or ""
            token_total = result.input_tokens + result.output_tokens
            trace_id = _trace_id_from_span(span)
        except Exception as e:
            logger.exception("chat_llm_failed thread_id=%s", thread_id)
            assistant_text = f"I could not complete this request: {e!s}."

    assistant_msg = ChatMessage(
        thread_id=thread.id,
        role="assistant",
        content=assistant_text,
        token_count=token_total,
        langfuse_trace_id=trace_id,
    )
    db.add(assistant_msg)
    thread.message_count = int(thread.message_count or 0) + 1
    await db.commit()
    await db.refresh(assistant_msg)
    await db.refresh(thread)

    text_out = assistant_text
    mid = assistant_msg.id

    async def event_stream():
        yield f"event: text\ndata: {json.dumps({'chunk': text_out})}\n\n"
        yield f"event: done\ndata: {json.dumps({'message_id': str(mid)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/actions/{action_id}/confirm", response_model=ActionResponse)
async def confirm_action(
    action_id: UUID,
    body: ActionConfirm,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ChatAction:
    u = await _get_or_create_user(db, org, user)
    q = await db.execute(
        select(ChatAction)
        .join(ChatThread, ChatThread.id == ChatAction.thread_id)
        .where(
            ChatAction.id == action_id,
            ChatThread.org_id == org.id,
            ChatThread.user_id == u.id,
            ChatAction.status == "proposed",
        )
    )
    action = q.scalar_one_or_none()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    if body.payload_edits:
        merged = dict(action.payload or {})
        merged.update(body.payload_edits)
        action.payload = merged

    try:
        out = await execute_action(action, db, org.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    action.status = "executed"
    action.result = out
    action.executed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(action)
    return action


@router.post("/actions/{action_id}/reject", response_model=ActionResponse)
async def reject_action(
    action_id: UUID,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ChatAction:
    u = await _get_or_create_user(db, org, user)
    q = await db.execute(
        select(ChatAction)
        .join(ChatThread, ChatThread.id == ChatAction.thread_id)
        .where(
            ChatAction.id == action_id,
            ChatThread.org_id == org.id,
            ChatThread.user_id == u.id,
            ChatAction.status == "proposed",
        )
    )
    action = q.scalar_one_or_none()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    action.status = "rejected"
    await db.commit()
    await db.refresh(action)
    return action
