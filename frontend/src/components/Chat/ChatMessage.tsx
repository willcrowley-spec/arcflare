import type { ChatMessage as ChatMessageRow } from '@/types'
import clsx from 'clsx'

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export function ChatMessage({ message }: { message: ChatMessageRow }) {
  const time = formatTime(message.created_at)

  if (message.role === 'system' || message.role === 'tool_result') {
    return (
      <div className="group flex justify-center px-2 py-1">
        <div
          title={time}
          className="max-w-[95%] rounded-md bg-slate-50 px-3 py-1.5 text-center text-xs text-slate-500 ring-1 ring-slate-200/80"
        >
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
          <span className="ml-2 hidden text-[10px] text-slate-400 group-hover:inline">{time}</span>
        </div>
      </div>
    )
  }

  if (message.role === 'user') {
    return (
      <div className="group flex justify-end px-2 py-1.5">
        <div
          title={time}
          className="max-w-[85%] rounded-2xl rounded-br-md bg-blue-50 px-4 py-2.5 text-sm leading-relaxed text-slate-800 shadow-sm ring-1 ring-blue-100/80"
        >
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
          <p className="mt-1 hidden text-right text-[10px] text-slate-400 group-hover:block">{time}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="group flex justify-start px-2 py-1.5">
      <div
        title={time}
        className={clsx(
          'max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-2.5 text-sm leading-relaxed text-slate-800 shadow-sm',
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        <p className="mt-1 hidden text-[10px] text-slate-400 group-hover:block">{time}</p>
      </div>
    </div>
  )
}
