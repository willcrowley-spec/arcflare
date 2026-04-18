# AI Chat Assistant & Process Gaps Panel

**Date:** 2026-04-17
**Status:** Draft

## Problem

Arcflare's process discovery engine identifies cross-domain gaps and builds hierarchical process maps, but users have no way to interact with these findings beyond viewing them. Gap cards are buried inside process maps, there's no conversational interface to ask questions about the discovered landscape, and refining process data requires manual record editing.

The platform needs two connected capabilities:
1. A **cross-domain gaps panel** that surfaces all identified gaps prominently on the Processes page with status tracking and remediation entry points.
2. An **AI chat assistant** that can answer questions about the process landscape, propose and execute mutations (create processes, resolve gaps, trigger re-synthesis), and ground its responses in the organization's own data via RAG.

## Design Principles

- **Anchored but free.** Contextual chat starts with pre-loaded context (a specific gap, process, or domain) but allows the user to navigate freely. The system classifies intent shifts and preserves prior context as retrievable state. Global chat has no anchor.
- **Confirm before invoke.** Every mutating action the AI proposes goes through an explicit user confirmation gate. Read-only operations execute automatically. This follows the Microsoft Agent Framework / OpenAI Agents SDK consensus for production HITL.
- **Private conversations, shared artifacts.** Chat threads are private to the user. Any `BusinessProcess` records, map updates, or gap resolutions made by the AI are visible to the entire organization — same as manual edits.
- **Observable by default.** Every chat request produces a Langfuse trace. Thread ID maps to Langfuse session ID. RAG retrieval, LLM calls, and tool executions each get their own spans.

## Industry Alignment

This design is informed by production patterns from:

| Pattern | Source | Our Implementation |
|---|---|---|
| Durable conversation container | OpenAI Conversations API, Gemini Session Service | `ChatThread` → `ChatMessage` |
| Function calling with structured declarations | Gemini Function Calling, Claude Tool Use | Tool registry with JSON Schema declarations |
| Confirm-before-invoke | Microsoft Agent Framework `ApprovalRequiredAIFunction`, OpenAI Agents SDK `needsApproval` | `ChatAction` with `proposed` → `confirmed` → `executed` lifecycle |
| Approve with edits | StackAI enterprise HITL research | Action cards support Confirm / Edit / Cancel |
| SSE streaming with mid-stream tool pauses | Gemini streaming + function calling, Claude SSE | `POST .../messages` returns SSE stream |
| Tiered tool risk | Arcade Tool Registry, COMPEL Framework | None (reads) / Inline (single writes) / Preview-then-commit (batches/deletes) |
| Parameter validation before surfacing | Iterathon production agents research (68% of failures are bad params) | Validation middleware between LLM output and action card |
| Session-scoped observability | Langfuse native conversation tracking | `session_id = thread_id`, nested spans |

## Data Model

### New Tables

#### `chat_threads`

Conversation container, scoped to a user within an org.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `org_id` | UUID FK → organizations | cascade delete |
| `user_id` | UUID FK → users | cascade delete — threads are private |
| `title` | String(255) | auto-generated from first message, editable |
| `anchor_type` | String(50), nullable | `gap`, `process`, `domain`, or null (global) |
| `anchor_id` | UUID, nullable | ID of the entity that spawned this thread |
| `model_override` | String(255), nullable | per-thread model override (null = use org default) |
| `summary` | Text, nullable | compressed summary of older messages for context window |
| `message_count` | Integer, default 0 | denormalized for list performance |
| `status` | String(50), default `active` | `active` / `archived` |
| `created_at` | DateTime(tz) | |
| `updated_at` | DateTime(tz) | |

#### `chat_messages`

Individual messages in a thread.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `thread_id` | UUID FK → chat_threads | cascade delete |
| `role` | String(20) | `user`, `assistant`, `system`, `tool_result` |
| `content` | Text | markdown for assistant, plain for user |
| `tool_calls` | JSONB, default `[]` | array of proposed tool calls from the LLM |
| `tool_results` | JSONB, default `[]` | results returned from tool execution |
| `token_count` | Integer, nullable | for context window management |
| `langfuse_trace_id` | String(255), nullable | links to Langfuse trace |
| `created_at` | DateTime(tz) | |

#### `chat_actions`

Every mutating action the AI proposes or executes. Full audit trail.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `thread_id` | UUID FK → chat_threads | |
| `message_id` | UUID FK → chat_messages | the assistant message that proposed this |
| `action_type` | String(50) | `create_process`, `update_process`, `delete_process`, `create_handoff`, `update_handoff`, `resolve_gap`, `rerun_synthesis` |
| `target_id` | UUID, nullable | the record being acted on (null for creates) |
| `payload` | JSONB | the proposed data (full create body or patch delta) |
| `status` | String(30) | `proposed` → `confirmed` → `executed` / `rejected` / `failed` |
| `result` | JSONB, nullable | execution result or error details |
| `idempotency_key` | String(100), unique | prevents double-execution on retries |
| `created_at` | DateTime(tz) | |
| `executed_at` | DateTime(tz), nullable | |

### Modified Tables

#### `process_handoffs` — new columns

| Column | Type | Notes |
|---|---|---|
| `gap_status` | String(30), default `open` | `open` / `investigating` / `resolved` |
| `resolution_note` | Text, nullable | how/why the gap was resolved |

## Operations Registry

New entry in `MODEL_OPERATIONS`:

```python
"chat": {
    "tier": "fast",
    "thinking_budget": 0,
    "output_format": "text",
    "label": "Chat Assistant",
    "group": "chat",
    "description": "Interactive process analyst assistant with function calling for actions. Fast model for responsive UX.",
},
```

New group in `OPERATION_GROUPS`: `"chat": "Chat Assistant"`.

The chat model is configurable on the Organization page alongside other operations. Users can override to `strong` for deeper reasoning or `lite` for cost savings.

## AI Tool System

### Tool Catalog

The AI receives tool declarations as function definitions. Each maps to a backend service method. Every invocation goes through the confirm-before-invoke gate unless marked auto-execute.

| Tool | Action Type | Risk | Auto-Execute | Description (3-4 sentences for LLM) |
|---|---|---|---|---|
| `search_knowledge` | read | None | Yes | Search the organization's document and metadata vector database. Use when the user asks factual questions about their platform, processes, or documents. Returns relevant chunks with source attribution. Do not use for process structure questions — use get_process_detail instead. |
| `get_process_detail` | read | None | Yes | Fetch the full detail of a specific business process including its children, handoffs, actors, and artifacts. Use when the user asks about a specific process or when you need to verify a process exists before proposing changes. Returns structured process data. |
| `list_gaps` | read | None | Yes | List all current cross-domain gaps (ProcessHandoffs where is_gap=true). Use when the user asks about gaps, missing connections, or problem areas. Returns gap details with source/target domains and confidence scores. Do not call this if you already have gap data in context. |
| `create_process` | create | Medium | No | Create a new BusinessProcess record. Requires name and description. Optional: category, parent_id (to nest under a domain/process), level, actors, artifacts. Use when the user identifies a missing process that should be added to the map. Always confirm the parent domain if creating a subprocess. |
| `update_process` | update | Medium | No | Update an existing BusinessProcess record by ID. Can modify name, description, status, category, confidence_score, narrative, actors, artifacts. Use when the user wants to refine or correct a discovered process. Only include fields that are changing. |
| `delete_process` | delete | High | No | Soft-delete a BusinessProcess and cascade to its children. Use only when the user explicitly asks to remove a process. Warn about child processes that will also be removed. This action cannot be undone. |
| `create_handoff` | create | Medium | No | Create a new ProcessHandoff between two processes. Requires source_process_id, target_process_id, handoff_type, and description. Use when the user identifies a connection between processes that is missing from the map. |
| `update_handoff` | update | Low | No | Update an existing ProcessHandoff's description, type, or confidence_score. Use when the user wants to refine a handoff's characterization. |
| `resolve_gap` | update | Low | No | Mark a cross-domain gap as resolved with a resolution note. Changes gap_status from open to resolved. Use when the user confirms a gap has been addressed or was a false positive. |
| `rerun_synthesis` | execute | Medium | No | Re-trigger Pass 3 (cross-domain synthesis) of the discovery pipeline. This re-evaluates all cross-domain handoffs and gaps based on current process data. Use when the user has made changes and wants to see if gaps are resolved or new ones appear. Takes several minutes to complete. |

### Confirmation Tiers

- **No confirmation** — read-only tools (`search_knowledge`, `get_process_detail`, `list_gaps`). Execute immediately, results flow into the conversation.
- **Inline confirmation** — single mutations (`create_process`, `update_process`, `create_handoff`, `update_handoff`, `resolve_gap`). AI proposes → user sees action card → Confirm / Edit / Cancel.
- **Preview-then-commit** — batch or high-impact operations (`delete_process`, `rerun_synthesis`). AI shows impact summary → user reviews → Commit or Abort.

### Parameter Validation Layer

Between LLM tool call output and user-facing action card:

1. Validate all referenced UUIDs exist in the database and belong to the current org.
2. Validate enum values (`handoff_type`, `level`, `status`) against allowed sets.
3. Validate parent-child relationship consistency (e.g., cannot create a subprocess under a step).
4. For `delete_process`: count children that would be cascaded, surface in the action card.
5. Reject invalid calls silently — the AI receives a tool error and can self-correct.

### Pre-Checks for High-Risk Operations

For `delete_process`:
- Count child processes and handoffs that reference this process.
- Surface in action card: "This will also remove 3 child processes and 2 handoffs."

For `rerun_synthesis`:
- Check if a discovery run is already in progress.
- Surface estimated duration based on process count.

## System Prompt Architecture

The AI's system prompt is assembled from layers:

1. **Persona** — "You are Arcflare's process analyst assistant. You help users understand, refine, and improve their business process maps. You have access to the organization's metadata, documents, and discovered processes."
2. **Tool definitions** — function declarations for each tool in the catalog.
3. **Guardrails** — "Always propose actions as tool calls, never claim you've done something without executing a tool. Never fabricate process data. If you're unsure, use search_knowledge or get_process_detail to verify. Be concise — this is a chat, not a report."
4. **Org context** — org name, industry, description (from `Organization.settings_json`).
5. **Anchor context** (contextual chat only) — the specific gap/process/domain JSON that launched this thread.
6. **Conversation history** — last N messages from the thread (sliding window, ~20 messages).
7. **Compressed history** — summary of older messages (stored in `ChatThread.summary`).

## API Endpoints

New router: `backend/app/api/routes/chat.py`, mounted at `/api/v1/chat`.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/threads` | List user's threads (paginated, most recent first) | User scoped |
| `POST` | `/threads` | Create new thread (optional `anchor_type`, `anchor_id`) | User scoped |
| `GET` | `/threads/{id}` | Get thread with recent messages | User scoped |
| `DELETE` | `/threads/{id}` | Archive thread (soft delete) | User scoped |
| `POST` | `/threads/{id}/messages` | Send message → SSE stream response | User scoped |
| `POST` | `/actions/{id}/confirm` | Confirm a proposed action (optional payload edits) | User scoped |
| `POST` | `/actions/{id}/reject` | Reject a proposed action | User scoped |

### Streaming Endpoint Flow (`POST /threads/{id}/messages`)

1. Persist user `ChatMessage` to database.
2. Build context: system prompt + anchor + last N messages + RAG retrieval.
3. Call LLM with tool definitions via streaming API.
4. Stream text chunks as SSE events: `event: text\ndata: {"chunk": "..."}\n\n`
5. If tool calls proposed → create `ChatAction` records in `proposed` status → stream action cards: `event: action\ndata: {"action_id": "...", "action_type": "...", "payload": {...}}\n\n`
6. Persist assistant `ChatMessage` with full content and tool_calls.
7. Final event: `event: done\ndata: {"message_id": "..."}\n\n`

### Langfuse Integration

Each chat request creates a Langfuse trace:

```
Trace: chat_request (session_id=thread.id, user_id=user.id)
├── Span: context_assembly (anchor, history, summary)
├── Span: rag_retrieval (query, result_count, latency)
├── Generation: llm_call (model, tokens_in, tokens_out, tool_calls)
├── Span: action_proposed (type, target_id, status=pending_user)  [0..N]
│   └── Span: action_executed (status, duration)                  [after confirm]
└── Span: response_persist (message_id, token_count)
```

## Process Gaps Panel (Frontend)

### Location & Behavior

New collapsible section above the search bar on the Processes page.

- **Expanded by default** if `kpis.gap_count > 0`, collapsed if zero.
- **Clicking the "Handoff Gaps" KPI card** auto-scrolls to and expands this section.
- **Header**: "Cross-Domain Gaps" with count badge and collapse toggle.

### Gap Card Contents

Each gap is a card displaying:
- **Source → Target**: Source domain name → Target domain name (bold, with arrow).
- **Description**: 2-3 line summary of the gap (from `ProcessHandoff.description`), with `line-clamp-3`.
- **Confidence badge**: color-coded (red < 0.5, amber 0.5-0.7, green > 0.7).
- **Status pill**: `open` (red) / `investigating` (amber) / `resolved` (green).
- **Actions**: "Chat with AI" button (opens contextual chat anchored to this gap) and "Dismiss" button (marks gap_status = resolved with a quick note).

### Pagination

If > 5 gaps, initially show 3 with "Show all X gaps" expand link. Fully expanded state persists in local storage.

## Chat Assistant (Frontend)

### Entry Points

1. **Global Chat**: Floating icon (bottom-right corner, all pages). Opens a slide-out panel (~400px wide) anchored to the right edge. Persists across page navigation via a Zustand store.
2. **Contextual Chat**: "Chat with AI" buttons on gap cards, process detail pages, and domain rows. Opens the same panel but pre-seeds a new thread with anchor context.

### Panel Components

- **Header**: Thread title (editable), model indicator pill, minimize/close buttons.
- **Thread drawer**: Small collapsible sidebar within the panel. Lists past threads (most recent first), "New thread" button.
- **Message area**: Standard chat bubbles. User right-aligned, assistant left-aligned. Markdown rendering for assistant messages. Structured action cards inline.
- **Action cards**: Rendered inline in the message flow. Show proposed changes with Confirm / Edit / Cancel buttons. Edit opens an inline form pre-filled with proposed data.
- **Input**: Text input with send button. No file upload for v1. Disabled while streaming.

### State Management

Zustand store (`useChatStore`):
- `isOpen: boolean`
- `activeThreadId: UUID | null`
- `threads: Thread[]`
- `messages: Map<UUID, Message[]>`
- `pendingActions: Map<UUID, Action>`
- `streamingMessageId: UUID | null`

React Query for data fetching (thread list, thread detail). EventSource hook for SSE streaming.

## What This Does NOT Include

- File upload in chat (future — share screenshots, docs for AI to analyze)
- Voice input (future)
- Multi-user shared threads (explicitly excluded — private conversations, shared artifacts)
- Chat history search (future — search across past threads)
- Automated gap remediation without user confirmation (violates HITL principle)
- Mobile-responsive chat panel (desktop-first for v1)
- Rate limiting on chat API (future — per-user token budgets)
