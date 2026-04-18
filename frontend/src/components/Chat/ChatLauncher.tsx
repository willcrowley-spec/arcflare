import { MessageSquare } from 'lucide-react'
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
        'fixed bottom-6 right-6 z-[60] flex h-14 w-14 items-center justify-center rounded-full bg-orange-500 text-white shadow-lg shadow-orange-500/25 transition-all hover:scale-105 hover:bg-orange-400 hover:shadow-orange-400/35 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-300 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-50',
        pending > 0 && 'animate-pulse',
      )}
    >
      <MessageSquare className="h-6 w-6" strokeWidth={1.75} />
      {pending > 0 ? (
        <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-white" aria-hidden />
      ) : null}
    </button>
  )
}
