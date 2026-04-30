import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChatMessage as ChatMessageRow, ArcResponse } from '@/types'
import { QuickReplyBar } from '@/components/Chat/QuickReplyBar'
import { OptionCardGroup } from '@/components/Chat/OptionCard'
import { SummaryCard } from '@/components/Chat/SummaryCard'
import { useTypewriter } from '@/hooks/useTypewriter'

function formatTimestamp(iso: string) {
  try {
    const d = new Date(iso)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    if (isToday) return time
    return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${time}`
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

function ArcBubble({
  text,
  time,
  displayedText,
  showCursor,
}: {
  text: string
  time: string
  displayedText?: string
  showCursor?: boolean
}) {
  const shown = displayedText ?? text
  return (
    <div className="flex justify-start px-2 py-1.5">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2 text-sm leading-relaxed text-slate-800 shadow-sm">
        <p className="whitespace-pre-wrap break-words">
          {shown}
          {showCursor ? <span className="inline-block h-3.5 w-[2px] animate-pulse bg-slate-400 align-text-bottom" /> : null}
        </p>
        <p className="mt-1 text-[10px] text-slate-400">{time}</p>
      </div>
    </div>
  )
}

interface Props {
  message: ChatMessageRow
  onQuickReply?: (text: string) => void
  /** When true, text reveals word-by-word and options reveal sequentially. */
  animate?: boolean
  /** Fires on each typewriter tick and option reveal — used by parent to auto-scroll. */
  onTick?: () => void
}

export function ChatMessage({ message, onQuickReply, animate, onTick }: Props) {
  const time = formatTimestamp(message.created_at)

  const arcResponse = useMemo(() => {
    if (message.role !== 'assistant') return null
    return tryParseArc(message.content)
  }, [message.role, message.content])

  const fullText = arcResponse
    ? arcResponse.type === 'question' || arcResponse.type === 'card_question'
      ? `${arcResponse.text}\n\n${arcResponse.question}`
      : arcResponse.text
    : message.content

  const { displayed, done: textDone } = useTypewriter(fullText, !!animate, onTick)
  const showCursor = !!animate && !textDone

  const onTickRef = useRef(onTick)
  onTickRef.current = onTick

  const optionCount = (arcResponse as { options?: unknown[] } | null)?.options?.length ?? 0

  // --- Sequential option reveal ---
  // -1 = waiting for text to finish, 0..n = which option is currently typewriting
  const [revealIndex, setRevealIndex] = useState(-1)

  useEffect(() => {
    if (!textDone || !animate || optionCount === 0) return
    if (revealIndex !== -1) return
    const timer = window.setTimeout(() => setRevealIndex(0), 280)
    return () => window.clearTimeout(timer)
  }, [textDone, animate, optionCount, revealIndex])

  // Scroll whenever a new option mounts
  useEffect(() => {
    if (revealIndex < 0) return
    const raf = requestAnimationFrame(() => onTickRef.current?.())
    return () => cancelAnimationFrame(raf)
  }, [revealIndex])

  const handleOptionRevealed = useCallback(() => {
    onTickRef.current?.()
    // Pause between options so the reader can absorb each one
    window.setTimeout(() => {
      setRevealIndex((i) => i + 1)
      onTickRef.current?.()
    }, 220)
  }, [])

  // --- Rendering ---

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
      <div className="flex justify-end px-2 py-1.5">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-navy-50 px-3.5 py-2 text-sm leading-relaxed text-navy-900 shadow-sm ring-1 ring-navy-100">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
          <p className="mt-1 text-right text-[10px] text-navy-500">{time}</p>
        </div>
      </div>
    )
  }

  if (!arcResponse) {
    return <ArcBubble text={message.content} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
  }

  const r = arcResponse
  const showControls = !animate || textDone

  if (r.type === 'message') {
    return <ArcBubble text={r.text} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
  }

  if (r.type === 'question') {
    return (
      <div>
        <ArcBubble text={`${r.text}\n\n${r.question}`} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
        {showControls ? (
          <QuickReplyBar
            options={r.options}
            onSelect={(opt) => onQuickReply?.(`[${opt.id.toUpperCase()}] ${opt.label}`)}
            revealUpTo={animate ? revealIndex : undefined}
            onOptionRevealed={handleOptionRevealed}
          />
        ) : null}
      </div>
    )
  }

  if (r.type === 'card_question') {
    return (
      <div>
        <ArcBubble text={`${r.text}\n\n${r.question}`} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
        {showControls ? (
          <OptionCardGroup
            options={r.options}
            onSelect={(opt) => onQuickReply?.(`[${opt.id.toUpperCase()}] ${opt.label}`)}
            revealUpTo={animate ? revealIndex : undefined}
            onOptionRevealed={handleOptionRevealed}
          />
        ) : null}
      </div>
    )
  }

  if (r.type === 'summary') {
    if (!showControls) {
      return <ArcBubble text={r.text} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
    }
    return (
      <div className={animate ? 'animate-[fade-in_300ms_ease-out]' : undefined}>
        <SummaryCard text={r.text} findings={r.findings} nextSteps={r.next_steps} />
      </div>
    )
  }

  if (r.type === 'action_proposal') {
    return <ArcBubble text={r.text} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
  }

  return <ArcBubble text={message.content} time={time} displayedText={animate ? displayed : undefined} showCursor={showCursor} />
}
