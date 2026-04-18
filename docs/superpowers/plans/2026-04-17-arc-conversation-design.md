# Arc Conversation Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the chat assistant from freeform prose into "Arc" — a structured, guided discovery agent that asks focused questions with interactive reply options.

**Architecture:** Backend rewrites the system prompt to enforce JSON-schema responses, switches the chat operation to JSON output mode, adds response validation and SSE phase events. Frontend adds 4 small components (ThinkingIndicator, QuickReplyBar, OptionCard, SummaryCard), modifies ChatMessage to parse structured JSON, and updates the header/launcher with Arc branding.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), Gemini JSON mode, existing SSE streaming.

**Spec:** `docs/superpowers/specs/2026-04-17-arc-conversation-design.md`

---

## File Map

### Backend — Modified
- `backend/app/core/config.py` — Add `ARC_AGENT_NAME` setting
- `backend/app/services/ai/operations.py` — Change chat operation `output_format` to `"json"`
- `backend/app/services/chat/context.py` — Full rewrite of `build_system_prompt()` with 3-layer Arc prompt + few-shot examples
- `backend/app/api/routes/chat.py` — Add `parse_arc_response()`, emit `event: status` SSE phase events, wire `action_proposal` to ChatAction creation

### Frontend — New
- `frontend/src/components/Chat/ThinkingIndicator.tsx` — Phase-aware thinking animation
- `frontend/src/components/Chat/QuickReplyBar.tsx` — Pill buttons for question options
- `frontend/src/components/Chat/OptionCard.tsx` — Radio-style cards for card_question options
- `frontend/src/components/Chat/SummaryCard.tsx` — Compact findings + next-steps card

### Frontend — Modified
- `frontend/src/components/Chat/ChatMessage.tsx` — Parse JSON, route to sub-components
- `frontend/src/components/Chat/ChatPanel.tsx` — ThinkingIndicator integration, Arc header, status SSE handling
- `frontend/src/components/Chat/ChatLauncher.tsx` — "Ask Arc" tooltip
- `frontend/src/hooks/useChat.ts` — Handle `event: status` SSE events
- `frontend/src/stores/chatStore.ts` — Add `agentName` and `thinkingPhase` state
- `frontend/src/types/index.ts` — Add `ArcResponse` type union

---

### Task 1: Backend Config + Operations

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/ai/operations.py`

- [ ] **Step 1: Add ARC_AGENT_NAME to Settings**

In `backend/app/core/config.py`, add after the `LANGFUSE_BASE_URL` line (line 65):

```python
    ARC_AGENT_NAME: str = Field(default="Arc", description="Display name for the chat agent")
```

- [ ] **Step 2: Change chat operation output_format to json**

In `backend/app/services/ai/operations.py`, change the `"chat"` entry from:

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

to:

```python
    "chat": {
        "tier": "fast",
        "thinking_budget": 0,
        "output_format": "json",
        "label": "Chat Assistant",
        "group": "chat",
        "description": "Guided discovery agent (Arc). Returns structured JSON responses for interactive UI rendering.",
    },
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py backend/app/services/ai/operations.py
git commit -m "feat(arc): add ARC_AGENT_NAME config, switch chat to JSON output mode"
```

---

### Task 2: System Prompt Rewrite

**Files:**
- Modify: `backend/app/services/chat/context.py`

- [ ] **Step 1: Replace build_system_prompt()**

Replace the entire `build_system_prompt` function in `backend/app/services/chat/context.py` with the three-layer Arc prompt. The function signature stays the same: `def build_system_prompt(org: Organization, tool_names: list[str]) -> str`.

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/chat/context.py
git commit -m "feat(arc): three-layer system prompt with structured JSON protocol and few-shot examples"
```

---

### Task 3: Response Validation + SSE Phase Events

**Files:**
- Modify: `backend/app/api/routes/chat.py`

- [ ] **Step 1: Add parse_arc_response function**

Add this function after the `_flatten_ctx` function (around line 63) in `backend/app/api/routes/chat.py`:

```python
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
```

- [ ] **Step 2: Add SSE status events to event_stream**

Inside the `event_stream()` async generator in `send_message` (line 279), emit `event: status` SSE events at two points.

**2a.** Before the `build_chat_context` call (before line 287), add:

```python
        yield f"event: status\ndata: {json.dumps({'phase': 'building_context'})}\n\n"
```

**2b.** After `build_gemini_tools` and before `asyncio.to_thread` (before line 340), add:

```python
        yield f"event: status\ndata: {json.dumps({'phase': 'thinking'})}\n\n"
```

- [ ] **Step 3: Parse and transform LLM response before SSE emission**

In the chunk processing loop (line 354-427), replace the text chunk handler. Change lines 356-358 from:

```python
                if chunk.type == "text" and chunk.text:
                    text_parts.append(chunk.text)
                    yield f"event: text\ndata: {json.dumps({'chunk': chunk.text})}\n\n"
```

to:

```python
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
```

The `parse_arc_response` validates and normalizes the raw LLM JSON. If the response is an `action_proposal`, a `ChatAction` record is created in the same block. The frontend receives validated, structured JSON as the text chunk, plus a separate `action` event for the ActionCard.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/chat.py
git commit -m "feat(arc): response validation, SSE phase events, action_proposal handling"
```

---

### Task 4: Frontend Types + Store Updates

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/hooks/useChat.ts`

- [ ] **Step 1: Add ArcResponse types**

Add to the bottom of `frontend/src/types/index.ts`:

```typescript
export type QuickOption = { id: string; label: string }
export type CardOption = { id: string; label: string; description: string }

export type ArcResponse =
  | { type: 'message'; text: string }
  | { type: 'question'; text: string; question: string; options: QuickOption[] }
  | { type: 'card_question'; text: string; question: string; options: CardOption[] }
  | { type: 'action_proposal'; text: string; action_type: string; payload: Record<string, unknown> }
  | { type: 'summary'; text: string; findings: string[]; next_steps: string[] }
```

- [ ] **Step 2: Add thinkingPhase and agentName to chatStore**

In `frontend/src/stores/chatStore.ts`, add three fields to the `ChatState` interface (after the `dismissedGaps` line):

```typescript
  agentName: string
  thinkingPhase: string | null
  setThinkingPhase: (phase: string | null) => void
```

Add to the `create` initializer (after `dismissedGaps: new Map(),`):

```typescript
  agentName: 'Arc',
  thinkingPhase: null,
  setThinkingPhase: (phase) => set({ thinkingPhase: phase }),
```

- [ ] **Step 3: Handle status SSE events in useChat**

In `frontend/src/hooks/useChat.ts`:

**3a.** Add `onStatus` to the `SseCallbacks` interface (after `onToolError`):

```typescript
  onStatus?: (phase: string) => void
```

**3b.** In the `handleSseBlock` function, add this block after the `tool_error` handler (after line 78):

```typescript
  if (eventName === 'status' && typeof payload === 'object' && payload !== null && 'phase' in payload) {
    const p = (payload as { phase?: string }).phase
    if (typeof p === 'string') callbacks.onStatus?.(p)
  }
```

**3c.** In `useSendMessage`, add `onStatus` to the destructured params (line 158):

```typescript
      onStatus,
```

Add to the params type:

```typescript
      onStatus?: (phase: string) => void
```

Add to the `consumeChatMessageStream` call (line 178):

```typescript
      await consumeChatMessageStream(res, { onDelta, onAction, onToolResult, onStatus })
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/stores/chatStore.ts frontend/src/hooks/useChat.ts
git commit -m "feat(arc): ArcResponse types, thinkingPhase store, status SSE handler"
```

---

### Task 5: ThinkingIndicator Component

**Files:**
- Create: `frontend/src/components/Chat/ThinkingIndicator.tsx`

- [ ] **Step 1: Create ThinkingIndicator**

```tsx
import { Loader2 } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'

const PHASE_LABELS: Record<string, string> = {
  building_context: 'Searching knowledge base…',
  thinking: '{name} is analyzing…',
}

export function ThinkingIndicator() {
  const phase = useChatStore((s) => s.thinkingPhase)
  const name = useChatStore((s) => s.agentName)

  if (!phase) return null

  const label = (PHASE_LABELS[phase] ?? `${name} is thinking…`).replace('{name}', name)

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-orange-500" />
      <span className="text-xs font-medium text-slate-500">{label}</span>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/ThinkingIndicator.tsx
git commit -m "feat(arc): ThinkingIndicator component with phase labels"
```

---

### Task 6: QuickReplyBar Component

**Files:**
- Create: `frontend/src/components/Chat/QuickReplyBar.tsx`

- [ ] **Step 1: Create QuickReplyBar**

```tsx
import { useState } from 'react'
import type { QuickOption } from '@/types'

interface QuickReplyBarProps {
  options: QuickOption[]
  onSelect: (option: QuickOption) => void
}

export function QuickReplyBar({ options, onSelect }: QuickReplyBarProps) {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <div className="mt-2 flex flex-wrap gap-1.5 px-2">
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          disabled={selected !== null}
          onClick={() => {
            setSelected(opt.id)
            onSelect(opt)
          }}
          className={
            'rounded-full border px-3 py-1.5 text-xs font-medium transition ' +
            (selected === opt.id
              ? 'border-orange-300 bg-orange-50 text-orange-800'
              : selected !== null
                ? 'border-slate-100 bg-slate-50 text-slate-400 cursor-default'
                : 'border-slate-200 bg-white text-slate-700 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-800')
          }
        >
          <span className="mr-1 font-semibold text-slate-400">{opt.id.toUpperCase()}</span>
          {opt.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/QuickReplyBar.tsx
git commit -m "feat(arc): QuickReplyBar component for question options"
```

---

### Task 7: OptionCard Component

**Files:**
- Create: `frontend/src/components/Chat/OptionCard.tsx`

- [ ] **Step 1: Create OptionCard group**

```tsx
import { useState } from 'react'
import clsx from 'clsx'
import type { CardOption } from '@/types'

interface OptionCardGroupProps {
  options: CardOption[]
  onSelect: (option: CardOption) => void
}

export function OptionCardGroup({ options, onSelect }: OptionCardGroupProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  return (
    <div className="mt-2 space-y-2 px-2">
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          disabled={submitted}
          onClick={() => setSelected(opt.id)}
          className={clsx(
            'flex w-full flex-col rounded-lg border p-3 text-left transition',
            selected === opt.id
              ? 'border-orange-300 bg-orange-50 ring-1 ring-orange-200'
              : submitted
                ? 'border-slate-100 bg-slate-50 opacity-60'
                : 'border-slate-200 bg-white hover:border-orange-200 hover:bg-orange-50/50',
          )}
        >
          <span className="text-sm font-semibold text-slate-800">
            <span className="mr-1.5 text-slate-400">{opt.id.toUpperCase()}.</span>
            {opt.label}
          </span>
          <span className="mt-0.5 text-xs leading-relaxed text-slate-500">{opt.description}</span>
        </button>
      ))}
      {selected && !submitted ? (
        <button
          type="button"
          onClick={() => {
            setSubmitted(true)
            const opt = options.find((o) => o.id === selected)
            if (opt) onSelect(opt)
          }}
          className="w-full rounded-lg bg-orange-500 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-orange-400"
        >
          Continue
        </button>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/OptionCard.tsx
git commit -m "feat(arc): OptionCardGroup component for card_question responses"
```

---

### Task 8: SummaryCard Component

**Files:**
- Create: `frontend/src/components/Chat/SummaryCard.tsx`

- [ ] **Step 1: Create SummaryCard**

```tsx
import { CheckCircle2, ArrowRight } from 'lucide-react'

interface SummaryCardProps {
  text: string
  findings: string[]
  nextSteps: string[]
}

export function SummaryCard({ text, findings, nextSteps }: SummaryCardProps) {
  return (
    <div className="mx-2 my-2 overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-b from-white to-slate-50/80 shadow-sm">
      <div className="px-4 py-3">
        <p className="text-sm leading-relaxed text-slate-700">{text}</p>
      </div>
      {findings.length > 0 ? (
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Findings</p>
          <ol className="space-y-1.5">
            {findings.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-700">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                <span>{f}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {nextSteps.length > 0 ? (
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Next Steps</p>
          <ol className="space-y-1.5">
            {nextSteps.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-700">
                <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-orange-500" />
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/SummaryCard.tsx
git commit -m "feat(arc): SummaryCard component for discovery summaries"
```

---

### Task 9: ChatMessage Structured Rendering

**Files:**
- Modify: `frontend/src/components/Chat/ChatMessage.tsx`

- [ ] **Step 1: Rewrite ChatMessage to parse Arc responses**

Replace the contents of `frontend/src/components/Chat/ChatMessage.tsx` with:

```tsx
import { useMemo } from 'react'
import type { ChatMessage as ChatMessageRow, ArcResponse } from '@/types'
import { QuickReplyBar } from '@/components/Chat/QuickReplyBar'
import { OptionCardGroup } from '@/components/Chat/OptionCard'
import { SummaryCard } from '@/components/Chat/SummaryCard'
import { useChatStore } from '@/stores/chatStore'
import clsx from 'clsx'

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

function tryParseArc(content: string): ArcResponse | null {
  if (!content) return null
  try {
    const parsed = JSON.parse(content)
    if (parsed && typeof parsed === 'object' && 'type' in parsed) return parsed as ArcResponse
  } catch {
    /* not structured — render as plain text */
  }
  return null
}

function ArcBubble({ text, time }: { text: string; time: string }) {
  return (
    <div className="group flex justify-start px-2 py-1.5">
      <div
        title={time}
        className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2 text-sm leading-relaxed text-slate-800 shadow-sm"
      >
        <p className="whitespace-pre-wrap break-words">{text}</p>
        <p className="mt-1 hidden text-[10px] text-slate-400 group-hover:block">{time}</p>
      </div>
    </div>
  )
}

interface Props {
  message: ChatMessageRow
  onQuickReply?: (text: string) => void
}

export function ChatMessage({ message, onQuickReply }: Props) {
  const time = formatTime(message.created_at)
  const agentName = useChatStore((s) => s.agentName)

  const arcResponse = useMemo(() => {
    if (message.role !== 'assistant') return null
    return tryParseArc(message.content)
  }, [message.role, message.content])

  if (message.role === 'system' || message.role === 'tool_result') {
    return (
      <div className="group flex justify-center px-2 py-1">
        <div
          title={time}
          className="max-w-[95%] rounded-md bg-slate-50 px-3 py-1.5 text-center text-xs text-slate-500 ring-1 ring-slate-200/80"
        >
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
        </div>
      </div>
    )
  }

  if (message.role === 'user') {
    return (
      <div className="group flex justify-end px-2 py-1.5">
        <div
          title={time}
          className="max-w-[85%] rounded-2xl rounded-br-md bg-blue-50 px-3.5 py-2 text-sm leading-relaxed text-slate-800 shadow-sm ring-1 ring-blue-100/80"
        >
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
          <p className="mt-1 hidden text-right text-[10px] text-slate-400 group-hover:block">{time}</p>
        </div>
      </div>
    )
  }

  if (!arcResponse) {
    return <ArcBubble text={message.content} time={time} />
  }

  const r = arcResponse

  if (r.type === 'message') {
    return <ArcBubble text={r.text} time={time} />
  }

  if (r.type === 'question') {
    return (
      <div>
        <ArcBubble text={`${r.text}\n\n${r.question}`} time={time} />
        <QuickReplyBar
          options={r.options}
          onSelect={(opt) => onQuickReply?.(`[${opt.id.toUpperCase()}] ${opt.label}`)}
        />
      </div>
    )
  }

  if (r.type === 'card_question') {
    return (
      <div>
        <ArcBubble text={`${r.text}\n\n${r.question}`} time={time} />
        <OptionCardGroup
          options={r.options}
          onSelect={(opt) => onQuickReply?.(`[${opt.id.toUpperCase()}] ${opt.label}`)}
        />
      </div>
    )
  }

  if (r.type === 'summary') {
    return <SummaryCard text={r.text} findings={r.findings} nextSteps={r.next_steps} />
  }

  if (r.type === 'action_proposal') {
    return <ArcBubble text={r.text} time={time} />
  }

  return <ArcBubble text={message.content} time={time} />
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/ChatMessage.tsx
git commit -m "feat(arc): ChatMessage parses structured JSON and routes to sub-components"
```

---

### Task 10: ChatPanel Integration

**Files:**
- Modify: `frontend/src/components/Chat/ChatPanel.tsx`
- Modify: `frontend/src/components/Chat/ChatLauncher.tsx`

- [ ] **Step 1: Replace ChatPanel.tsx with Arc-integrated version**

Replace the entire file `frontend/src/components/Chat/ChatPanel.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  List,
  Loader2,
  MessageSquareText,
  Plus,
  SendHorizontal,
  Sparkles,
  Trash2,
} from 'lucide-react'
import clsx from 'clsx'
import { useChatStore } from '@/stores/chatStore'
import {
  useConfirmAction,
  useCreateThread,
  useDeleteThread,
  useRejectAction,
  useSendMessage,
  useThread,
  useThreads,
} from '@/hooks/useChat'
import type { ChatAction, ChatMessage as ChatMessageRow } from '@/types'
import type { StreamAction } from '@/hooks/useChat'
import { ActionCard } from '@/components/Chat/ActionCard'
import { ChatMessage } from '@/components/Chat/ChatMessage'
import { ThinkingIndicator } from '@/components/Chat/ThinkingIndicator'

export function ChatPanel() {
  const isOpen = useChatStore((s) => s.isOpen)
  const closeChat = useChatStore((s) => s.closeChat)
  const activeThreadId = useChatStore((s) => s.activeThreadId)
  const setActiveThread = useChatStore((s) => s.setActiveThread)
  const anchorContext = useChatStore((s) => s.anchorContext)
  const consumeInitialPrompt = useChatStore((s) => s.consumeInitialPrompt)
  const setPendingActionsCount = useChatStore((s) => s.setPendingActionsCount)
  const setThinkingPhase = useChatStore((s) => s.setThinkingPhase)
  const agentName = useChatStore((s) => s.agentName)

  const [threadMenu, setThreadMenu] = useState(false)
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const [streamingActions, setStreamingActions] = useState<StreamAction[]>([])
  const [sendError, setSendError] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const didSendInitialRef = useRef(false)

  const { data: threads = [], isLoading: threadsLoading } = useThreads()
  const { data: detail, isLoading: detailLoading, isFetching } = useThread(activeThreadId)

  const createThread = useCreateThread()
  const deleteThread = useDeleteThread()
  const sendMessage = useSendMessage(activeThreadId)
  const confirmAction = useConfirmAction()
  const rejectAction = useRejectAction()

  useEffect(() => {
    const proposed = (detail?.pending_actions ?? []).filter((a) => a.status === 'proposed')
    setPendingActionsCount(proposed.length)
  }, [detail?.pending_actions, setPendingActionsCount])

  useEffect(() => {
    if (!isOpen) {
      setStreamingText('')
      setSendError(null)
      setThreadMenu(false)
      setThinkingPhase(null)
      didSendInitialRef.current = false
    }
  }, [isOpen, setThinkingPhase])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [streamingText, detail?.messages])

  const handleSend = useCallback(
    async (overrideText?: string) => {
      const text = (overrideText ?? input).trim()
      if (!text || sendMessage.isPending || createThread.isPending) return
      setSendError(null)
      setStreamingText('')
      setStreamingActions([])
      setThinkingPhase('thinking')

      let tid = activeThreadId
      try {
        if (!tid) {
          const thread = await createThread.mutateAsync({
            title: text.slice(0, 80),
            anchor_type: anchorContext?.type ?? null,
            anchor_id: anchorContext?.id ?? null,
          })
          tid = thread.id
          setActiveThread(thread.id)
        }
        if (!overrideText) setInput('')
        await sendMessage.mutateAsync({
          threadId: tid,
          content: text,
          onDelta: (chunk) => {
            setThinkingPhase(null)
            setStreamingText((s) => s + chunk)
          },
          onAction: (action) => setStreamingActions((prev) => [...prev, action]),
          onStatus: (phase) => setThinkingPhase(phase),
        })
        setStreamingText('')
        setStreamingActions([])
        setThinkingPhase(null)
      } catch (e) {
        setSendError(e instanceof Error ? e.message : 'Failed to send')
        setStreamingText('')
        setStreamingActions([])
        setThinkingPhase(null)
      }
    },
    [activeThreadId, anchorContext?.id, anchorContext?.type, createThread, input, sendMessage, setActiveThread, setThinkingPhase],
  )

  useEffect(() => {
    if (isOpen && !didSendInitialRef.current) {
      const prompt = consumeInitialPrompt()
      if (prompt) {
        didSendInitialRef.current = true
        void handleSend(prompt)
      }
    }
  }, [isOpen, consumeInitialPrompt, handleSend])

  const handleDeleteThread = useCallback(
    async (id: string) => {
      await deleteThread.mutateAsync(id)
      if (activeThreadId === id) setActiveThread(null)
    },
    [activeThreadId, deleteThread, setActiveThread],
  )

  const handleQuickReply = useCallback(
    (text: string) => {
      setInput(text)
      setTimeout(() => void handleSend(text), 50)
    },
    [handleSend],
  )

  const sortedMessages = useMemo(() => {
    const m = detail?.messages ?? []
    return [...m].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  }, [detail?.messages])

  const proposedByMessageId = useMemo(() => {
    const map = new Map<string, ChatAction[]>()
    for (const a of detail?.pending_actions ?? []) {
      if (a.status !== 'proposed') continue
      const list = map.get(a.message_id) ?? []
      list.push(a)
      map.set(a.message_id, list)
    }
    return map
  }, [detail?.pending_actions])

  const threadMismatch = Boolean(activeThreadId && detail?.thread.id !== activeThreadId)
  const threadTitle =
    threadMismatch || !detail?.thread ? (activeThreadId ? 'Loading…' : 'New chat') : detail.thread.title

  const hasMessages = sortedMessages.length > 0 || !!streamingText

  if (!isOpen) return null

  return (
    <div
      className={clsx(
        'fixed bottom-20 right-5 z-50 flex flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-2xl shadow-slate-900/12',
        'w-[min(96vw,420px)]',
        hasMessages ? 'h-[min(85vh,600px)]' : 'h-auto max-h-[min(85vh,600px)]',
        'animate-[chat-pop_200ms_ease-out]',
      )}
      style={{ transformOrigin: 'bottom right' }}
    >
      {/* Header */}
      <header className="flex shrink-0 items-center gap-2 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-500 text-white shadow-sm">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-800">{agentName}</p>
          {activeThreadId && detail?.thread ? (
            <p className="truncate text-[11px] text-slate-500">{detail.thread.title}</p>
          ) : anchorContext ? (
            <p className="truncate text-[11px] text-orange-600">
              {anchorContext.type} context
            </p>
          ) : null}
        </div>
        <div className="relative">
          <button
            type="button"
            onClick={() => setThreadMenu((p) => !p)}
            className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            aria-label="Thread menu"
          >
            <List className="h-4 w-4" />
          </button>
          {threadMenu ? (
            <>
              <button
                type="button"
                className="fixed inset-0 z-10"
                onClick={() => setThreadMenu(false)}
                aria-hidden
              />
              <div className="absolute right-0 top-full z-20 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl">
                <button
                  type="button"
                  onClick={() => {
                    setActiveThread(null)
                    setThreadMenu(false)
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50"
                >
                  <Plus className="h-4 w-4 text-slate-400" />
                  New conversation
                </button>
                <div className="my-1 border-t border-slate-100" />
                {threadsLoading ? (
                  <div className="flex justify-center py-3">
                    <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                  </div>
                ) : threads.length === 0 ? (
                  <p className="px-3 py-2 text-xs text-slate-400">No previous threads</p>
                ) : (
                  <div className="max-h-48 space-y-0.5 overflow-y-auto">
                    {threads.map((t) => (
                      <div
                        key={t.id}
                        className={clsx(
                          'group flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition',
                          t.id === activeThreadId ? 'bg-orange-50 text-orange-800' : 'hover:bg-slate-50',
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => {
                            setActiveThread(t.id)
                            setThreadMenu(false)
                          }}
                          className="min-w-0 flex-1 text-left"
                        >
                          <p className="truncate text-xs font-medium">{t.title || 'Untitled'}</p>
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            void handleDeleteThread(t.id)
                          }}
                          className="shrink-0 rounded p-0.5 text-slate-400 opacity-0 transition hover:text-red-500 group-hover:opacity-100"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </header>

      {/* Messages area */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {!activeThreadId && !detailLoading ? (
          <div className="flex flex-col items-center px-6 py-10 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-50 text-orange-500">
              <MessageSquareText className="h-6 w-6" strokeWidth={1.5} />
            </div>
            <p className="mt-3 text-sm font-semibold text-slate-800">{agentName}</p>
            <p className="mt-1.5 max-w-[260px] text-xs leading-relaxed text-slate-500">
              Ask about processes, gaps, and handoffs. I can also create and modify process records for you.
            </p>
            <div className="mt-5 grid w-full gap-2">
              {[
                'What are the open cross-domain gaps?',
                'Summarize the discovered processes',
                'Help me resolve a process gap',
              ].map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => {
                    setInput(q)
                    inputRef.current?.focus()
                  }}
                  className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2 text-left text-xs text-slate-600 transition hover:border-orange-200 hover:bg-orange-50/50 hover:text-orange-700"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {activeThreadId && (detailLoading || isFetching) && (!detail || threadMismatch) ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
          </div>
        ) : null}

        {activeThreadId && detail && !threadMismatch ? (
          <div className="px-1 py-3">
            {sortedMessages.length === 0 && !streamingText ? (
              <p className="px-4 py-6 text-center text-xs text-slate-400">Send a message to start…</p>
            ) : (
              sortedMessages.map((m: ChatMessageRow) => (
                <div key={m.id}>
                  <ChatMessage message={m} onQuickReply={handleQuickReply} />
                  {(proposedByMessageId.get(m.id) ?? []).map((a) => (
                    <ActionCard
                      key={a.id}
                      action={a}
                      onConfirm={async (payload) => {
                        await confirmAction.mutateAsync({ actionId: a.id, body: payload })
                      }}
                      onReject={async () => {
                        await rejectAction.mutateAsync(a.id)
                      }}
                    />
                  ))}
                </div>
              ))
            )}

            {streamingText ? (
              <div className="group flex justify-start px-2 py-1.5">
                <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2 text-sm leading-relaxed text-slate-800 shadow-sm">
                  <p className="whitespace-pre-wrap break-words">{streamingText}</p>
                  <span className="mt-1 inline-flex items-center gap-1 text-[10px] text-orange-500">
                    <Loader2 className="h-2.5 w-2.5 animate-spin" /> Generating
                  </span>
                </div>
              </div>
            ) : null}

            <ThinkingIndicator />

            {streamingActions.map((sa) => (
              <div key={sa.action_id} className="px-2 py-1.5">
                <ActionCard
                  action={{
                    id: sa.action_id,
                    thread_id: '',
                    message_id: '',
                    action_type: sa.action_type,
                    target_id: sa.target_id,
                    payload: sa.payload,
                    status: 'proposed',
                    result: null,
                    idempotency_key: '',
                    created_at: new Date().toISOString(),
                    executed_at: null,
                  }}
                  onConfirm={async (payload) => {
                    await confirmAction.mutateAsync({ actionId: sa.action_id, body: payload })
                    setStreamingActions((prev) => prev.filter((a) => a.action_id !== sa.action_id))
                  }}
                  onReject={async () => {
                    await rejectAction.mutateAsync(sa.action_id)
                    setStreamingActions((prev) => prev.filter((a) => a.action_id !== sa.action_id))
                  }}
                />
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-100 bg-white px-3 py-2.5">
        {sendError ? (
          <p className="mb-1.5 rounded-md bg-red-50 px-2 py-1 text-xs font-medium text-red-600">{sendError}</p>
        ) : null}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void handleSend()
              }
            }}
            rows={1}
            placeholder={`Message ${agentName}…`}
            className="min-h-[38px] max-h-24 flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-sm text-slate-800 shadow-inner shadow-slate-900/5 placeholder:text-slate-400 focus:border-orange-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-400/20"
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={sendMessage.isPending || createThread.isPending || !input.trim()}
            className="inline-flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-orange-500 text-white shadow-sm transition hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Send"
          >
            {sendMessage.isPending || createThread.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <SendHorizontal className="h-4 w-4" strokeWidth={2} />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
```

Key changes from original:
- Added `ThinkingIndicator` import + rendering (between streaming text and streaming actions)
- Added `agentName` and `setThinkingPhase` from store
- `handleSend` calls `setThinkingPhase('thinking')` immediately on send
- `onDelta` clears thinking phase (so indicator disappears on first text)
- `onStatus` callback pipes SSE phase events to store
- Both success and catch blocks call `setThinkingPhase(null)`
- Added `handleQuickReply` callback, passed via `onQuickReply` prop to `ChatMessage`
- Header shows `agentName` as primary text, thread title as subtitle
- Placeholder says `Message ${agentName}…`
- Empty state shows `{agentName}` instead of "Arcflare Assistant"
- `isOpen` cleanup effect also resets `thinkingPhase`

- [ ] **Step 2: Replace ChatLauncher.tsx with Arc-branded version**

Replace the entire file `frontend/src/components/Chat/ChatLauncher.tsx`:

```tsx
import { MessageSquare, X } from 'lucide-react'
import clsx from 'clsx'
import { useChatStore } from '@/stores/chatStore'

export function ChatLauncher() {
  const isOpen = useChatStore((s) => s.isOpen)
  const openChat = useChatStore((s) => s.openChat)
  const closeChat = useChatStore((s) => s.closeChat)
  const pending = useChatStore((s) => s.pendingActionsCount)
  const name = useChatStore((s) => s.agentName)

  return (
    <button
      type="button"
      onClick={() => (isOpen ? closeChat() : openChat())}
      title={isOpen ? `Close ${name}` : `Ask ${name}`}
      aria-label={isOpen ? `Close ${name}` : `Ask ${name}`}
      className={clsx(
        'fixed bottom-5 right-5 z-[60] flex h-13 w-13 items-center justify-center rounded-full shadow-lg transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-300 focus-visible:ring-offset-2',
        isOpen
          ? 'bg-slate-700 text-white hover:bg-slate-600'
          : 'bg-orange-500 text-white hover:scale-105 hover:bg-orange-400 shadow-orange-500/30',
        pending > 0 && !isOpen && 'animate-pulse',
      )}
    >
      {isOpen ? (
        <X className="h-5 w-5" strokeWidth={2} />
      ) : (
        <MessageSquare className="h-5.5 w-5.5" strokeWidth={1.75} />
      )}
      {pending > 0 && !isOpen ? (
        <span className="absolute -right-0.5 -top-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white ring-2 ring-white">
          {pending > 9 ? '9+' : pending}
        </span>
      ) : null}
    </button>
  )
}
```

Key changes: Added `name` from store, `title` attribute, updated `aria-label` to use agent name.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatPanel.tsx frontend/src/components/Chat/ChatLauncher.tsx
git commit -m "feat(arc): integrate ThinkingIndicator, quick replies, and Arc branding"
```

---

### Task 11: Push and Verify

- [ ] **Step 1: Push all changes**

```bash
git push origin master
```

- [ ] **Step 2: Verify on Railway**

After deploy completes (~3 min):
1. Navigate to Processes page
2. Click "Chat with AI" on a gap
3. Verify: ThinkingIndicator appears → phase labels update → Arc responds with structured JSON → QuickReplyBar renders with clickable options
4. Click an option → verify it sends as the next message → Arc asks follow-up question
5. Complete the discovery flow through to a summary response
