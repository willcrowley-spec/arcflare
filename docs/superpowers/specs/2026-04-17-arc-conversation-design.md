# Arc Conversation Design Spec

**Date:** 2026-04-17
**Status:** Approved
**Scope:** Redesign the Arcflare chat assistant ("Arc") from freeform text output to a structured, guided discovery agent focused on process gap resolution.

## Problem

The current chat assistant dumps lengthy consulting-report-style prose when the user asks about a gap. No discovery phase, no structured questions, no interaction — just a wall of text. The user wanted guided collaboration; they got an essay.

Root causes:
- System prompt says "prefer concise" but doesn't enforce it
- No structured output schema — LLM defaults to freeform prose
- No conversation workflow — LLM jumps to recommendations without discovery
- No thinking indicator — 10+ second dead silence before response
- No agent identity — generic "Arcflare Assistant" label

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Process gap analyst (expandable to broader copilot) | Cisco research: tightly scoped agents hallucinate less, earn more trust |
| Build approach | Custom (no library) | Problem is conversation design, not components. We have the plumbing. |
| Interaction style | Hybrid: quick-reply buttons + structured cards | Microsoft/GitHub Copilot pattern. Always allow freeform typing alongside. |
| Agent name | "Arc" | Derived from Arcflare. One syllable. Configurable via env var. |
| Persona | Senior process analyst. Asks questions, doesn't lecture. | Anthropic's agent identity research: anchored role reduces improvisation. |

## 1. Structured Response Protocol

Arc responds exclusively in structured JSON. The frontend parses the response `type` and renders the corresponding component.

### Response Schema

```typescript
type ArcResponse =
  | { type: "message"; text: string }
  | { type: "question"; text: string; question: string; options: QuickOption[] }
  | { type: "card_question"; text: string; question: string; options: CardOption[] }
  | { type: "action_proposal"; text: string; action_type: string; payload: Record<string, unknown> }
  | { type: "summary"; text: string; findings: string[]; next_steps: string[] }

type QuickOption = { id: string; label: string }
type CardOption = { id: string; label: string; description: string }
```

### Rendering Map

| `type` | Frontend Component |
|--------|-------------------|
| `message` | Text bubble (2-3 sentences max) |
| `question` | Text bubble + `QuickReplyBar` (2-5 pill buttons) |
| `card_question` | Text bubble + `OptionCard` group (radio-style cards with descriptions) |
| `action_proposal` | Text bubble + existing `ActionCard` (confirm/edit/reject) |
| `summary` | Compact card: findings list + next-steps list |

### Example Exchange

**User** (via contextual gap prompt):
> I'm looking at a cross-domain gap between "Direct Sales Opportunity Management" and "Customer Onboarding & Provisioning"...

**Arc** responds:
```json
{
  "type": "question",
  "text": "This gap is about what happens after a deal closes — how does the customer actually get provisioned? Let me help figure this out.",
  "question": "Do you know what happens today when an opportunity is marked closed-won?",
  "options": [
    {"id": "a", "label": "There's an automated flow in Salesforce"},
    {"id": "b", "label": "Someone manually hands it off"},
    {"id": "c", "label": "I'm not sure — that's part of the problem"},
    {"id": "d", "label": "Nothing happens — it's broken"}
  ]
}
```

### `action_proposal` and Tool Calling

The `action_proposal` response type is Arc's way of *describing* a proposed action in the conversation. When the backend receives an `action_proposal` response, it creates a `ChatAction` record (status: "proposed") using the existing action lifecycle — identical to how Gemini function calls create actions today. The frontend renders the existing `ActionCard` component. This means `action_proposal` is a structured-output alternative to function calling for the same underlying flow; both paths converge on the same `ChatAction` → confirm/reject → execute pipeline.

### Fallback

If the LLM returns invalid JSON (schema violation or parse failure), the backend wraps it as `{"type": "message", "text": "<raw text>"}`. The UI never breaks — worst case is an unstructured text bubble.

## 2. System Prompt Architecture

Three layers following the Anthropic/OpenAI 7-component best practice.

### Layer 1 — Identity & Style

```
You are Arc, a senior process analyst embedded in the Arcflare platform.
Your name is {agent_name}.

Communication rules:
- You work WITH the user to resolve process gaps. You do not lecture.
- Keep all text fields under 3 sentences.
- Ask one question at a time. Wait for the answer before continuing.
- Never dump analysis unprompted. Discovery first, action second.
- When uncertain, say so. Never fabricate data or IDs.
```

### Layer 2 — Structured Output Protocol

```
You MUST respond with valid JSON matching exactly one of these types:

1. "message" — A short observation or acknowledgment.
   {type: "message", text: string}

2. "question" — You need the user's input. Include 2-5 options.
   {type: "question", text: string, question: string, options: [{id, label}]}

3. "card_question" — A complex choice where options need explanation.
   {type: "card_question", text: string, question: string, options: [{id, label, description}]}

4. "action_proposal" — You want to perform a platform action.
   {type: "action_proposal", text: string, action_type: string, payload: object}

5. "summary" — Wrap up a discovery phase with findings and next steps.
   {type: "summary", text: string, findings: [string], next_steps: [string]}

Rules:
- Respond with exactly ONE JSON object per turn. No arrays, no markdown, no prose outside JSON.
- Never combine multiple types in one response.
- Options should always include a freeform escape (e.g., "Something else" or "I'm not sure").
```

### Layer 3 — Gap Discovery Workflow

```
When the conversation is anchored to a process gap, follow this sequence:

Step 1 — ACKNOWLEDGE: Confirm what gap you're looking at in one sentence. (type: message)
Step 2 — DISCOVER CURRENT STATE: Ask what happens today. 1-2 questions. (type: question)
Step 3 — ASSESS IMPACT: Ask about severity, frequency, or business impact. (type: question)
Step 4 — PROPOSE RESOLUTION: Suggest 1-2 specific actions using platform tools. (type: action_proposal or card_question)
Step 5 — SUMMARIZE: Recap findings and agreed next steps. (type: summary)

Do NOT skip to Step 4 without completing Steps 1-3.
If the user goes off-topic, address their question, then guide back to the workflow.
```

### Few-Shot Examples

Include 1-2 complete user→Arc exchanges in the system prompt demonstrating correct schema usage. These serve as concrete output format anchors and improve structured output compliance by 20-30% per research.

Example 1: A `question` response with options.
Example 2: A `summary` response with findings and next_steps.

(Exact examples written at implementation time based on real gap data.)

## 3. Frontend Components

### New: `ThinkingIndicator`

- Appears within 300ms of message send (client-side timer, no server dependency)
- Displays "{agent_name} is thinking..." with pulse animation
- Updates text when `event: status` SSE events arrive:
  - `{"phase": "building_context"}` → "Searching knowledge base..."
  - `{"phase": "thinking"}` → "Arc is analyzing..."
- Disappears when first `event: text` arrives
- ~15 lines of React

### New: `QuickReplyBar`

- Renders below assistant bubble for `type: "question"` responses
- 2-5 pill-shaped buttons, horizontally wrapping
- Click sends the option label as the user's next message (prefixed: `"[A] There's an automated flow..."`)
- Buttons disable after selection or after user types manually
- Text input always remains available alongside buttons
- ~40 lines of React

### New: `OptionCard`

- Renders for `type: "card_question"` responses
- Radio-style card group: each option has bold label + description line
- User selects one, clicks "Continue" button
- Can also type freely to override
- ~60 lines of React

### New: `SummaryCard`

- Renders for `type: "summary"` responses
- Compact card with:
  - Brief text header
  - "Findings" — numbered list
  - "Next Steps" — numbered list with action-oriented language
- ~50 lines of React

### Modified: `ChatMessage`

- Parses assistant message `content` as JSON
- Routes to sub-component based on `type` field
- Fallback: if JSON parse fails, renders as plain text bubble (existing behavior)

### Modified: `ChatPanel` Header

- Displays `{agent_name}` (from env var via API) instead of thread title
- Status indicator next to name: idle (green dot), thinking (orange pulse), responding (streaming dots)
- Thread title moves to a subtitle line below the name

### Modified: `ChatLauncher`

- Tooltip on hover: "Ask {agent_name}"

## 4. Backend Changes

### System Prompt Rewrite (`context.py`)

- Replace `build_system_prompt()` with the three-layer prompt described in Section 2
- Insert `{agent_name}` from `settings.ARC_AGENT_NAME`
- Include few-shot examples for `question` and `summary` response types

### Chat Operation Config (`operations.py`)

- Change `"chat"` operation `output_format` from `"text"` to `"json"`
- This enables `response_mime_type="application/json"` in Gemini config, enforcing valid JSON at the API level
- `thinking_budget` remains `0` (structured output, no thinking needed)

### Response Validation (`chat.py`)

- New function `parse_arc_response(text: str) -> dict`:
  - Parse JSON
  - Validate `type` is one of the 5 allowed values
  - Validate required fields per type
  - Fallback: `{"type": "message", "text": raw_text}` on any failure
- Called after LLM response, before SSE emission

### SSE Phase Events (`chat.py`)

- Emit `event: status` SSE events during pre-LLM work:
  - Before `build_chat_context()`: `{"phase": "building_context"}`
  - Before LLM call: `{"phase": "thinking"}`
- Frontend `ThinkingIndicator` consumes these

### Config (`config.py`)

- New setting: `ARC_AGENT_NAME: str = Field(default="Arc")`
- Exposed via existing `/api/v1/organization` response or a lightweight `/api/v1/chat/config` endpoint

### No Changes To

- Tool calling / function declarations
- Action lifecycle (propose → confirm/reject → execute)
- Langfuse tracing
- ChatThread / ChatMessage / ChatAction models
- Alembic migrations (no schema changes)

## 5. Data Flow

Full lifecycle when user clicks "Chat with AI" on a gap:

1. **Frontend**: `openContextualChat({type: "gap", id}, prompt)`. Bubble opens. Contextual prompt consumed and sent. User message appears immediately (optimistic UI).
2. **Frontend**: `ThinkingIndicator` shows "Arc is thinking..." within 300ms.
3. **Backend**: `send_message` persists user message. Starts `event_stream()`.
4. **Backend → SSE**: `event: status {"phase": "building_context"}`. Frontend → "Searching knowledge base..."
5. **Backend**: `build_chat_context()` assembles structured prompt + anchor + RAG.
6. **Backend → SSE**: `event: status {"phase": "thinking"}`. Frontend → "Arc is analyzing..."
7. **Backend**: LLM call via `asyncio.to_thread()`. Gemini returns complete JSON (JSON mode, not streaming).
8. **Backend**: `parse_arc_response()` validates. Falls back to message type on failure.
9. **Backend → SSE**: `event: text {"chunk": "<full JSON>"}`. Then `event: done`.
10. **Frontend**: `ChatMessage` parses JSON, renders `QuickReplyBar` / `OptionCard` / `ActionCard` / `SummaryCard`.
11. **Frontend**: ThinkingIndicator disappears. Interactive components are live.
12. **User**: Clicks option or types freely. Cycle repeats.

### Streaming Trade-off

JSON mode returns complete responses (not token-by-token). This is intentional — partial JSON can't render as buttons. The SSE phase indicators fill perceived wait time. Research on the "trust-latency gap" supports this: users trust visible process over fast but opaque delivery.

## 6. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARC_AGENT_NAME` | `"Arc"` | Display name for the agent in UI and prompts |

## 7. Success Criteria

- Gap conversations follow the 5-step discovery workflow (acknowledge → discover → assess → propose → summarize)
- Arc never outputs more than 3 sentences of prose per turn
- Quick-reply buttons render on every `question` response
- ThinkingIndicator appears within 300ms and shows phase labels
- Freeform typing always works alongside structured options
- Invalid LLM JSON falls back gracefully to text bubble (never crashes)
- Zero new npm dependencies
