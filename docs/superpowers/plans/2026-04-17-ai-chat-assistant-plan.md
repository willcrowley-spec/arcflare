# AI Chat Assistant — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-17-ai-chat-assistant-design.md`
**Date:** 2026-04-17

## Phase 1: Foundation (Models, Migration, Registry)

### 1.1 — SQLAlchemy models
- Create `backend/app/models/chat.py` with `ChatThread`, `ChatMessage`, `ChatAction` models.
- Follow existing patterns from `process.py` and `discovery.py` (UUID PK, JSONB, FK cascades).
- Add `gap_status` (String(30), default `open`) and `resolution_note` (Text, nullable) columns to `ProcessHandoff` in `discovery.py`.
- Update `backend/app/models/__init__.py` to export new models.

### 1.2 — Alembic migration
- Single migration creating `chat_threads`, `chat_messages`, `chat_actions` tables.
- Add `gap_status` and `resolution_note` to `process_handoffs`.
- Unique index on `chat_actions.idempotency_key`.
- Indexes on `chat_threads.user_id`, `chat_threads.org_id`, `chat_messages.thread_id`.

### 1.3 — Operations registry update
- Add `"chat"` operation to `MODEL_OPERATIONS` in `operations.py` (tier: fast, thinking: 0, output: text).
- Add `"chat": "Chat Assistant"` to `OPERATION_GROUPS`.

### 1.4 — Pydantic schemas
- Create `backend/app/schemas/chat.py` with request/response models:
  - `ThreadCreate`, `ThreadResponse`, `ThreadListResponse`
  - `MessageCreate`, `MessageResponse`
  - `ActionResponse`, `ActionConfirm`
- Update `backend/app/schemas/discovery.py`: add `gap_status` and `resolution_note` to `ProcessHandoffResponse`.

## Phase 2: Chat API (Backend Core)

### 2.1 — Chat router CRUD
- Create `backend/app/api/routes/chat.py` with router mounted at `/api/v1/chat`.
- `GET /threads` — list user's threads, paginated, most recent first.
- `POST /threads` — create thread (optional `anchor_type`, `anchor_id`, `model_override`).
- `GET /threads/{id}` — get thread with last 50 messages.
- `DELETE /threads/{id}` — archive thread (set status=archived).
- Register router in `backend/app/api/routes/__init__.py`.

### 2.2 — Tool registry
- Create `backend/app/services/chat/tools.py` defining tool declarations as dicts (name, description, parameters JSON Schema).
- 10 tools: `search_knowledge`, `get_process_detail`, `list_gaps`, `create_process`, `update_process`, `delete_process`, `create_handoff`, `update_handoff`, `resolve_gap`, `rerun_synthesis`.
- Each tool has: `auto_execute: bool`, `risk_level: str`, `handler: Callable`.

### 2.3 — Parameter validation middleware
- Create `backend/app/services/chat/validation.py`.
- `validate_tool_call(tool_name, params, org_id, db) -> (valid: bool, errors: list[str])`.
- Checks: UUID existence, org scoping, enum validation, parent-child consistency.
- For `delete_process`: returns cascade impact count.

### 2.4 — Context assembly
- Create `backend/app/services/chat/context.py`.
- `build_chat_context(thread, messages, org, anchor_data) -> list[dict]` — assembles the system prompt layers.
- Sliding window: last 20 messages from thread.
- RAG retrieval: semantic search against org's vector DB using the user's latest message.
- Anchor context: if thread has `anchor_type`/`anchor_id`, fetch the entity and include as context.

### 2.5 — Streaming message endpoint
- `POST /threads/{id}/messages` — accepts user message, returns SSE stream.
- Flow: persist user message → build context → call LLM with tools → stream text chunks → handle tool calls → persist assistant message.
- SSE event types: `text` (chunk), `action` (proposed tool call), `error`, `done`.
- Use FastAPI `StreamingResponse` with `text/event-stream` content type.
- Call LLM via existing `llm_call` from `router.py` with `operation="chat"`.

### 2.6 — Action confirm/reject endpoints
- `POST /actions/{id}/confirm` — optional payload edits, executes the action.
- `POST /actions/{id}/reject` — sets status to rejected.
- Action execution calls the appropriate service method (create/update/delete BusinessProcess, resolve gap, etc.).
- Idempotency: check `idempotency_key` to prevent double-execution.

## Phase 3: Langfuse Integration

### 3.1 — Trace per chat request
- Wrap the streaming endpoint logic in `langfuse_span(name="chat_request", session_id=str(thread.id))`.
- Nest `rag_retrieval` span for vector search.
- Use `langfuse_generation` for the LLM call with model, token counts, tool_calls.
- Store `langfuse_trace_id` on the persisted `ChatMessage`.

### 3.2 — Action execution spans
- When an action is confirmed and executed, create a `langfuse_span(name="action_executed")` linked to the original trace via `thread.id` session.
- Log action type, target_id, execution duration, success/failure.

## Phase 4: Frontend — Chat UI Shell

### 4.1 — Zustand store & types
- Create `frontend/src/stores/chatStore.ts` with `useChatStore`.
- State: `isOpen`, `activeThreadId`, `threads`, `pendingActions`, `streamingMessageId`.
- Actions: `openChat`, `openContextualChat`, `closeChat`, `setActiveThread`, `addPendingAction`, `resolvePendingAction`.
- Add TypeScript types to `frontend/src/types/index.ts` or `frontend/src/types/chat.ts`.

### 4.2 — API hooks
- Create `frontend/src/hooks/useChat.ts` with React Query hooks:
  - `useThreads()` — list threads.
  - `useThread(id)` — get thread with messages.
  - `useCreateThread()` — create thread mutation.
  - `useDeleteThread()` — archive thread mutation.
  - `useSendMessage()` — send message + SSE streaming via EventSource.
  - `useConfirmAction()` / `useRejectAction()` — action mutations.

### 4.3 — ChatPanel component
- Create `frontend/src/components/Chat/ChatPanel.tsx`.
- Slide-out panel, 400px, right-anchored. Animated open/close.
- Header: thread title, model pill, minimize/close.
- Thread drawer: collapsible list of past threads, new thread button.
- Message area: scrollable, auto-scroll to bottom on new messages.
- Input: text area with send button, disabled while streaming.

### 4.4 — ChatMessage component
- Create `frontend/src/components/Chat/ChatMessage.tsx`.
- User messages: right-aligned, bg-blue-50 bubble.
- Assistant messages: left-aligned, bg-white bubble, markdown rendered.
- Tool result messages: compact, system-styled.

### 4.5 — ActionCard component
- Create `frontend/src/components/Chat/ActionCard.tsx`.
- Renders proposed action with structured data display.
- Buttons: Confirm (green), Edit (amber), Cancel (gray).
- Edit mode: inline form pre-filled with proposed payload.
- Impact warnings for delete operations (child count).
- Loading state while action executes.

### 4.6 — ChatLauncher component
- Create `frontend/src/components/Chat/ChatLauncher.tsx`.
- Floating button, bottom-right, `fixed` positioning.
- Badge for unread/pending actions.
- Click toggles `useChatStore.isOpen`.
- Add to root layout so it appears on all pages.

### 4.7 — SSE streaming hook
- Create `frontend/src/hooks/useChatStream.ts`.
- EventSource connection to `POST /threads/{id}/messages`.
- Handles `text`, `action`, `error`, `done` event types.
- Progressive message assembly (append text chunks to current message).
- Auto-creates pending action entries in Zustand store when `action` events arrive.

## Phase 5: Frontend — Gaps Panel

### 5.1 — Gaps API endpoint
- Add `GET /api/v1/processes/gaps` to `processes.py` router.
- Returns all `ProcessHandoff` where `is_gap=true` for the org, with source/target process names resolved via joins.
- Include `gap_status`, `resolution_note`, `confidence_score`.

### 5.2 — GapsPanel component
- Create `frontend/src/pages/Processes/GapsPanel.tsx`.
- Collapsible section above search bar on Processes page.
- Expanded by default if gaps > 0.
- Each gap card: source → target, description (line-clamp-3), confidence badge, status pill.
- "Chat with AI" button → `useChatStore.openContextualChat({ anchor_type: 'gap', anchor_id: gap.id })`.
- "Dismiss" button → PATCH to update `gap_status = 'resolved'` with quick note dialog.
- Pagination: show 3 initially, "Show all X gaps" expand.

### 5.3 — Integrate on Processes page
- Import `GapsPanel` into `frontend/src/pages/Processes/index.tsx`.
- Place above the search bar.
- Wire "Handoff Gaps" KPI card click to scroll to and expand GapsPanel.
- Add "Chat with AI" button to domain accordion rows and process detail.

## Phase 6: Tool Execution Layer

### 6.1 — Tool handler service
- Create `backend/app/services/chat/actions.py`.
- `execute_action(action: ChatAction, db: AsyncSession, org_id: UUID) -> dict` — dispatch to the correct handler based on `action_type`.
- Each handler is a thin wrapper around existing service methods:
  - `create_process` → create `BusinessProcess` via existing patterns.
  - `update_process` → patch `BusinessProcess` fields.
  - `delete_process` → soft-delete with child cascade.
  - `create_handoff` → create `ProcessHandoff`.
  - `update_handoff` → patch `ProcessHandoff` fields.
  - `resolve_gap` → update `gap_status` and `resolution_note` on `ProcessHandoff`.
  - `rerun_synthesis` → dispatch `process_discovery_task` with pass3-only config.
- Idempotency check: if action already executed (by idempotency_key), return cached result.
- All mutations within a single database transaction.

### 6.2 — Pre-execution checks
- For `delete_process`: count children and handoffs. Include in action result for the card.
- For `rerun_synthesis`: check for active discovery runs. Reject if one is running.
- For all mutations: verify org scoping on target records.

### 6.3 — Graph refresh after mutations
- After any process/handoff mutation via chat, trigger a lightweight graph rebuild for affected domains.
- Reuse `generate_graphs_for_run` logic from `graph.py` scoped to the changed domain.

## Phase 7: Integration & Polish

### 7.1 — Organization page update
- Add chat model to the model configuration grid on the Organization page.
- It should appear alongside existing operations with the same override UI.

### 7.2 — Edge cases
- Handle thread not found (404).
- Handle streaming disconnection (EventSource reconnect with backoff).
- Handle action confirmation timeout (auto-expire proposed actions after 30 minutes).
- Handle concurrent action confirmations on the same record (optimistic locking via updated_at).
- Empty state: no threads yet → friendly prompt in thread drawer.
- Empty state: no gaps → collapsed panel with "No gaps identified" message.

### 7.3 — Accessibility & UX polish
- Keyboard navigation in chat (Enter to send, Shift+Enter for newline).
- Focus management when panel opens/closes.
- Scroll-to-bottom on new messages with manual scroll override.
- Loading skeletons for thread list and message loading.
- Subtle animation on action card confirmation (green flash).
- Escape key closes chat panel.

## Dependency Order

```
Phase 1 (foundation) → Phase 2 (API) → Phase 3 (Langfuse)
                                      → Phase 4 (chat UI) → Phase 5 (gaps panel)
                     → Phase 6 (tool execution) [after Phase 2]
                                                → Phase 7 (polish) [after all]
```

Phases 3, 4, and 6 can proceed in parallel once Phase 2 is complete.
