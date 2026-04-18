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
