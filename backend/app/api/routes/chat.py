"""AI chat assistant HTTP API (threads, messages, actions)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentOrg, CurrentUserDep, DbSession, get_or_create_org_user
from app.core.observability import langfuse_context, langfuse_generation, langfuse_span
from app.models.chat import ChatAction, ChatMessage, ChatThread
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
from app.services.chat.actions import execute_action, execute_auto_tool
from app.services.chat.context import build_chat_context
from app.services.chat.tools import get_openai_tools, get_tool
from app.services.chat.validation import validate_tool_call
from app.services.ai.router import (
    ChatStreamChunk,
    llm_call,
    stream_chat_with_tools,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _trace_id_from_span(span: object | None) -> str | None:
    if span is None:
        return None
    for attr in ("trace_id", "traceId", "id"):
        tid = getattr(span, attr, None)
        if tid:
            return str(tid)
    return None


def _flatten_ctx(ctx: list[dict]) -> str:
    """Flatten message dicts into a single prompt string for non-streaming fallback."""
    blocks = []
    for m in ctx:
        role = str(m.get("role", "user")).upper()
        content = str(m.get("content", ""))
        blocks.append(f"[{role}]\n{content}")
    return "\n\n".join(blocks)


_VALID_ARC_TYPES = frozenset({"message", "question", "card_question", "action_proposal", "summary"})

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "message": ["text"],
    "question": ["text", "question", "options"],
    "card_question": ["text", "question", "options"],
    "action_proposal": ["text", "action_type", "payload"],
    "summary": ["text", "findings", "next_steps"],
}


def parse_arc_response(raw: str) -> dict:
    """Validate LLM JSON against Arc response schema. Falls back to plain message on any failure."""
    if not raw or not raw.strip():
        return {"type": "message", "text": "I wasn't able to generate a response. Could you rephrase?"}
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return {"type": "message", "text": raw.strip()}

    if not isinstance(data, dict):
        return {"type": "message", "text": raw.strip()}

    resp_type = data.get("type")
    if resp_type not in _VALID_ARC_TYPES:
        return {"type": "message", "text": data.get("text", raw.strip())}

    required = _REQUIRED_FIELDS.get(resp_type, [])
    for field in required:
        if field not in data:
            return {"type": "message", "text": data.get("text", raw.strip())}

    return data


def _collect_stream_chunks(
    ctx: list[dict],
    tools: list[dict] | None,
    analysis_config: dict | None,
) -> list[ChatStreamChunk]:
    """Run sync streaming/LLM work (call from ``asyncio.to_thread``)."""
    if tools is not None:
        return list(
            stream_chat_with_tools(
                messages=ctx,
                tools=tools,
                max_tokens=4096,
                operation="chat",
                model_config=analysis_config,
            )
        )

    result = llm_call(
        _flatten_ctx(ctx),
        max_tokens=4096,
        tier="fast",
        operation="chat",
        model_config=analysis_config,
    )
    return [
        ChatStreamChunk(type="text", text=result.text, model=result.model),
        ChatStreamChunk(
            type="done",
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        ),
    ]


@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: ThreadCreate,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ChatThread:
    u = await get_or_create_org_user(db, org, user)
    thread = ChatThread(
        org_id=org.id,
        user_id=u.id,
        title=body.title or "New conversation",
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
    u = await get_or_create_org_user(db, org, user)
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
    u = await get_or_create_org_user(db, org, user)
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
    u = await get_or_create_org_user(db, org, user)
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
    u = await get_or_create_org_user(db, org, user)
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

    thread_id_str = str(thread.id)
    org_id = org.id
    analysis_config = org.analysis_config
    user_msg_id = user_msg.id

    async def event_stream():
        text_parts: list[str] = []
        tool_calls_collected: list[dict] = []
        actions_created: list[dict] = []
        total_tokens = 0
        trace_id: str | None = None

        try:
            yield f"event: status\ndata: {json.dumps({'phase': 'building_context'})}\n\n"
            ctx = await build_chat_context(
                thread, db, org, body.content, exclude_message_id=user_msg.id,
            )
        except Exception as prep_exc:
            logger.exception("chat_context_build_failed thread=%s", thread_id_str)
            yield (
                "event: error\ndata: "
                + json.dumps({"error": str(prep_exc), "code": "context_build_failed"})
                + "\n\n"
            )
            err_text = f"I could not prepare this reply: {prep_exc!s}"
            yield f"event: text\ndata: {json.dumps({'chunk': err_text})}\n\n"
            assistant_msg = ChatMessage(
                thread_id=UUID(thread_id_str),
                role="assistant",
                content=err_text,
                tool_calls=[],
                token_count=None,
                langfuse_trace_id=None,
            )
            db.add(assistant_msg)
            thread_obj = await db.get(ChatThread, UUID(thread_id_str))
            if thread_obj:
                thread_obj.message_count = int(thread_obj.message_count or 0) + 1
            await db.commit()
            await db.refresh(assistant_msg)
            yield f"event: done\ndata: {json.dumps({'message_id': str(assistant_msg.id)})}\n\n"
            return

        chat_tools: list[dict] | None = None
        try:
            chat_tools = get_openai_tools(thread.anchor_type)
        except Exception as tools_exc:
            logger.warning(
                "get_openai_tools_failed thread=%s err=%s", thread_id_str, tools_exc,
            )
            chat_tools = None

        org_id_str = str(thread.org_id)

        with langfuse_context(
            user_id=str(u.id), org_id=org_id_str, session_id=str(thread.id),
        ):
            with langfuse_span(
                name="chat_request",
                metadata={"user_id": str(u.id), "thread_id": str(thread.id)},
            ) as span:
                trace_id = _trace_id_from_span(span)

                chunks: list[ChatStreamChunk] = []
                yield f"event: status\ndata: {json.dumps({'phase': 'thinking'})}\n\n"
                try:
                    chunks = await asyncio.to_thread(
                        _collect_stream_chunks, ctx, chat_tools, analysis_config,
                    )
                except Exception as collect_exc:
                    logger.exception("chat_stream_collect_failed thread=%s", thread_id_str)
                    yield (
                        "event: error\ndata: "
                        + json.dumps({"error": str(collect_exc), "code": "stream_collect_failed"})
                        + "\n\n"
                    )
                    err_text = f"Stream error: {collect_exc!s}"
                    text_parts.append(err_text)
                    yield f"event: text\ndata: {json.dumps({'chunk': err_text})}\n\n"

                try:
                    for chunk in chunks:
                        if chunk.type == "text" and chunk.text:
                            text_parts.append(chunk.text)
                            parsed = parse_arc_response(chunk.text)
                            yield f"event: text\ndata: {json.dumps({'chunk': json.dumps(parsed)})}\n\n"

                            if parsed.get("type") == "action_proposal":
                                ap_action_type = str(parsed.get("action_type", ""))
                                ap_payload = parsed.get("payload") or {}
                                if ap_action_type:
                                    idem_key = f"{thread_id_str}:{user_msg_id}:arc_proposal:{ap_action_type}"
                                    action = ChatAction(
                                        thread_id=UUID(thread_id_str),
                                        message_id=user_msg_id,
                                        action_type=ap_action_type,
                                        target_id=_extract_target_id(ap_payload),
                                        payload=ap_payload,
                                        status="proposed",
                                        idempotency_key=idem_key[:100],
                                    )
                                    db.add(action)
                                    await db.commit()
                                    await db.refresh(action)
                                    action_data = {
                                        "action_id": str(action.id),
                                        "action_type": action.action_type,
                                        "target_id": str(action.target_id) if action.target_id else None,
                                        "payload": action.payload,
                                        "status": "proposed",
                                    }
                                    actions_created.append(action_data)
                                    yield f"event: action\ndata: {json.dumps(action_data)}\n\n"

                        elif chunk.type == "function_call":
                            tool_def = get_tool(chunk.function_name, thread.anchor_type)
                            if not tool_def:
                                logger.warning("unknown_tool_call name=%s", chunk.function_name)
                                continue

                            tc_record = {
                                "name": chunk.function_name,
                                "args": chunk.function_args or {},
                                "call_id": chunk.function_call_id,
                            }
                            tool_calls_collected.append(tc_record)

                            if tool_def["auto_execute"]:
                                try:
                                    result = await execute_auto_tool(
                                        chunk.function_name,
                                        chunk.function_args or {},
                                        org_id,
                                        db,
                                    )
                                    yield f"event: tool_result\ndata: {json.dumps({'tool': chunk.function_name, 'result': result})}\n\n"
                                except Exception as exc:
                                    logger.warning(
                                        "auto_tool_failed name=%s err=%s", chunk.function_name, exc,
                                    )
                                    yield f"event: tool_result\ndata: {json.dumps({'tool': chunk.function_name, 'error': str(exc)})}\n\n"
                            else:
                                valid, errors, enriched = await validate_tool_call(
                                    chunk.function_name,
                                    chunk.function_args or {},
                                    org_id,
                                    db,
                                )
                                if not valid:
                                    yield f"event: tool_error\ndata: {json.dumps({'tool': chunk.function_name, 'errors': errors})}\n\n"
                                    continue

                                idem_key = (
                                    f"{thread_id_str}:{user_msg_id}:"
                                    f"{chunk.function_name}:{chunk.function_call_id}"
                                )
                                action = ChatAction(
                                    thread_id=UUID(thread_id_str),
                                    message_id=user_msg_id,
                                    action_type=chunk.function_name,
                                    target_id=_extract_target_id(enriched),
                                    payload=enriched,
                                    status="proposed",
                                    idempotency_key=idem_key[:100],
                                )
                                db.add(action)
                                await db.commit()
                                await db.refresh(action)

                                action_data = {
                                    "action_id": str(action.id),
                                    "action_type": action.action_type,
                                    "target_id": str(action.target_id) if action.target_id else None,
                                    "payload": action.payload,
                                    "status": "proposed",
                                    "cascade_info": enriched.get("_cascade_info"),
                                }
                                actions_created.append(action_data)
                                yield f"event: action\ndata: {json.dumps(action_data)}\n\n"

                        elif chunk.type == "done":
                            total_tokens = chunk.input_tokens + chunk.output_tokens

                        elif chunk.type == "error":
                            text_parts.append(f"\n\nI encountered an error: {chunk.text}")
                            yield f"event: text\ndata: {json.dumps({'chunk': f'I encountered an error: {chunk.text}'})}\n\n"

                except Exception as exc:
                    logger.exception("chat_stream_failed thread=%s", thread_id_str)
                    yield (
                        "event: error\ndata: "
                        + json.dumps({"error": str(exc), "code": "stream_failed"})
                        + "\n\n"
                    )
                    err_text = f"Stream error: {exc!s}"
                    text_parts.append(err_text)
                    yield f"event: text\ndata: {json.dumps({'chunk': err_text})}\n\n"

                full_response_text = "".join(text_parts)

                done_chunks = [c for c in chunks if c.type == "done"]
                if done_chunks:
                    dc = done_chunks[-1]
                    with langfuse_generation(
                        name="chat_completion",
                        model=dc.model,
                        input=body.content[:500],
                    ) as gen:
                        if gen is not None:
                            cost_details = None
                            try:
                                import litellm as _ll
                                ic = _ll.cost_per_token(model=dc.model, prompt_tokens=dc.input_tokens, completion_tokens=0)
                                oc = _ll.cost_per_token(model=dc.model, prompt_tokens=0, completion_tokens=dc.output_tokens)
                                cost_details = {
                                    "input": ic[0] if isinstance(ic, tuple) else ic,
                                    "output": oc[1] if isinstance(oc, tuple) else oc,
                                }
                            except Exception:
                                pass
                            gen.update(
                                output=full_response_text[:1000] if full_response_text else "",
                                usage_details={
                                    "input": dc.input_tokens,
                                    "output": dc.output_tokens,
                                },
                                cost_details=cost_details,
                            )

                assistant_msg = ChatMessage(
                    thread_id=UUID(thread_id_str),
                    role="assistant",
                    content=full_response_text,
                    tool_calls=tool_calls_collected or [],
                    token_count=total_tokens or None,
                    langfuse_trace_id=trace_id,
                )
                db.add(assistant_msg)

                for action_data in actions_created:
                    try:
                        act = await db.get(ChatAction, UUID(action_data["action_id"]))
                        if act:
                            act.message_id = assistant_msg.id
                    except Exception:
                        pass

                thread_obj = await db.get(ChatThread, UUID(thread_id_str))
                if thread_obj:
                    thread_obj.message_count = int(thread_obj.message_count or 0) + 1

                await db.commit()
                await db.refresh(assistant_msg)

                yield f"event: done\ndata: {json.dumps({'message_id': str(assistant_msg.id)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _extract_target_id(params: dict) -> UUID | None:
    """Pull the first UUID-shaped target from tool params."""
    for key in ("process_id", "handoff_id", "target_process_id", "source_process_id", "recommendation_id"):
        val = params.get(key)
        if val:
            try:
                return UUID(str(val))
            except (ValueError, AttributeError):
                pass
    return None


@router.post("/actions/{action_id}/confirm", response_model=ActionResponse)
async def confirm_action(
    action_id: UUID,
    body: ActionConfirm,
    db: DbSession,
    org: CurrentOrg,
    user: CurrentUserDep,
) -> ChatAction:
    u = await get_or_create_org_user(db, org, user)
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
    u = await get_or_create_org_user(db, org, user)
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
