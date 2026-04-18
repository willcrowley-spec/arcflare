import { MessageSquare, X } from 'lucide-react'
import clsx from 'clsx'
import { useChatStore } from '@/stores/chatStore'

export function ChatLauncher() {
  const isOpen = useChatStore((s) => s.isOpen)
  const openChat = useChatStore((s) => s.openChat)
  const closeChat = useChatStore((s) => s.closeChat)
  const pending = useChatStore((s) => s.pendingActionsCount)

  return (
    <button
      type="button"
      onClick={() => (isOpen ? closeChat() : openChat())}
      aria-label={isOpen ? 'Close assistant' : 'Open assistant'}
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
