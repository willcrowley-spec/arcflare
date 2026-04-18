import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ChevronLeft,
  Loader2,
  MessageSquareText,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  SendHorizontal,
  Trash2,
  X,
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
import { ActionCard } from '@/components/Chat/ActionCard'
import { ChatMessage } from '@/components/Chat/ChatMessage'

export function ChatPanel() {
  const isOpen = useChatStore((s) => s.isOpen)
  const closeChat = useChatStore((s) => s.closeChat)
  const activeThreadId = useChatStore((s) => s.activeThreadId)
  const setActiveThread = useChatStore((s) => s.setActiveThread)
  const anchorContext = useChatStore((s) => s.anchorContext)
  const setPendingActionsCount = useChatStore((s) => s.setPendingActionsCount)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const [sendError, setSendError] = useState<string | null>(null)

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
    }
  }, [isOpen])

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
    threadMismatch || !detail?.thread ? (activeThreadId ? 'Loading…' : 'New conversation') : detail.thread.title
  const modelLabel =
    threadMismatch || !detail?.thread ? 'Default model' : detail.thread.model_override?.trim() || 'Default model'

  const handleNewThread = useCallback(() => {
    setActiveThread(null)
    setDrawerOpen(true)
  }, [setActiveThread])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || sendMessage.isPending || createThread.isPending) return
    setSendError(null)
    setStreamingText('')

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
      setInput('')
      await sendMessage.mutateAsync({
        threadId: tid,
        content: text,
        onDelta: (chunk) => setStreamingText((s) => s + chunk),
      })
      setStreamingText('')
    } catch (e) {
      setSendError(e instanceof Error ? e.message : 'Failed to send')
      setStreamingText('')
    }
  }, [
    activeThreadId,
    anchorContext?.id,
    anchorContext?.type,
    createThread,
    input,
    sendMessage,
    setActiveThread,
  ])

  const handleDeleteThread = useCallback(
    async (id: string) => {
      await deleteThread.mutateAsync(id)
      if (activeThreadId === id) {
        setActiveThread(null)
      }
    },
    [activeThreadId, deleteThread, setActiveThread],
  )

  const panelWidthClass = drawerOpen ? 'w-[min(100vw,600px)]' : 'w-[min(100vw,400px)]'

  return (
    <>
      <button
        type="button"
        aria-hidden={!isOpen}
        tabIndex={isOpen ? 0 : -1}
        className={clsx(
          'fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-[1px] transition-opacity duration-300',
          isOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={closeChat}
      />

      <aside
        aria-hidden={!isOpen}
        className={clsx(
          'fixed right-0 top-0 z-50 flex h-full flex-col border-l border-slate-200 bg-white shadow-2xl shadow-slate-900/10 transition-transform duration-300 ease-out',
          panelWidthClass,
          isOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none',
        )}
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-slate-100 px-3 py-3">
          <button
            type="button"
            onClick={() => setDrawerOpen((o) => !o)}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            aria-label={drawerOpen ? 'Hide threads' : 'Show threads'}
          >
            {drawerOpen ? <PanelRightClose className="h-5 w-5" /> : <PanelRightOpen className="h-5 w-5" />}
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-800">{threadTitle}</p>
            <div className="mt-0.5 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200/80">
                {modelLabel}
              </span>
              {anchorContext ? (
                <span className="rounded-full bg-orange-50 px-2 py-0.5 text-[11px] font-medium text-orange-800 ring-1 ring-orange-200/80">
                  {anchorContext.type}:{anchorContext.id.slice(0, 8)}…
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={handleNewThread}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            aria-label="Start new thread"
          >
            <Plus className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={closeChat}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            aria-label="Close panel"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          {drawerOpen ? (
            <nav className="flex w-[200px] shrink-0 flex-col border-r border-slate-100 bg-slate-50/80">
              <div className="flex items-center justify-between border-b border-slate-100 px-2 py-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Threads</span>
                <ChevronLeft className="h-4 w-4 text-slate-400" aria-hidden />
              </div>
              <div className="flex-1 overflow-y-auto p-1.5">
                {threadsLoading ? (
                  <div className="flex justify-center py-6">
                    <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                  </div>
                ) : threads.length === 0 ? (
                  <p className="px-2 py-4 text-center text-xs text-slate-500">No threads yet</p>
                ) : (
                  <ul className="space-y-1">
                    {threads.map((t) => (
                      <li key={t.id}>
                        <div
                          className={clsx(
                            'group flex items-start gap-1 rounded-lg border border-transparent px-2 py-1.5 transition',
                            t.id === activeThreadId ? 'border-slate-200 bg-white shadow-sm' : 'hover:bg-white',
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => setActiveThread(t.id)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <p className="truncate text-xs font-semibold text-slate-800">{t.title || 'Untitled'}</p>
                            <p className="text-[10px] text-slate-500">{t.message_count} msgs</p>
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              void handleDeleteThread(t.id)
                            }}
                            className="shrink-0 rounded p-1 text-slate-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                            aria-label="Delete thread"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </nav>
          ) : null}

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto px-1 py-3">
              {!activeThreadId && !detailLoading ? (
                <div className="mx-auto flex max-w-sm flex-col items-center px-4 py-12 text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-50 text-orange-600 ring-1 ring-orange-100">
                    <MessageSquareText className="h-6 w-6" strokeWidth={1.5} />
                  </span>
                  <p className="mt-4 text-sm font-semibold text-slate-800">Arcflare Assistant</p>
                  <p className="mt-2 text-xs leading-relaxed text-slate-500">
                    Ask about processes, gaps, and handoffs. Your first message creates a thread anchored to your
                    current context when available.
                  </p>
                </div>
              ) : null}

              {activeThreadId && (detailLoading || isFetching) && (!detail || threadMismatch) ? (
                <div className="flex justify-center py-16">
                  <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                </div>
              ) : null}

              {activeThreadId && detail && !threadMismatch ? (
                sortedMessages.length === 0 && !streamingText ? (
                  <p className="px-4 py-8 text-center text-sm text-slate-500">No messages yet — send a prompt below.</p>
                ) : (
                  sortedMessages.map((m: ChatMessageRow) => (
                    <div key={m.id}>
                      <ChatMessage message={m} />
                      {(proposedByMessageId.get(m.id) ?? []).map((a) => (
                        <ActionCard
                          key={a.id}
                          action={a}
                          onConfirm={async (payload) => {
                            await confirmAction.mutateAsync({
                              actionId: a.id,
                              body: payload,
                            })
                          }}
                          onReject={async () => {
                            await rejectAction.mutateAsync(a.id)
                          }}
                        />
                      ))}
                    </div>
                  ))
                )
              ) : null}

              {streamingText ? (
                <div className="group flex justify-start px-2 py-1.5">
                  <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-2.5 text-sm leading-relaxed text-slate-800 shadow-sm">
                    <p className="whitespace-pre-wrap break-words">{streamingText}</p>
                    <p className="mt-1 text-[10px] text-orange-500">Generating…</p>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="shrink-0 border-t border-slate-100 bg-white p-3">
              {sendError ? <p className="mb-2 text-xs font-medium text-red-600">{sendError}</p> : null}
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      void handleSend()
                    }
                  }}
                  rows={2}
                  placeholder="Message…"
                  className="min-h-[44px] flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-sm text-slate-800 shadow-inner shadow-slate-900/5 placeholder:text-slate-400 focus:border-orange-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-400/25"
                />
                <button
                  type="button"
                  onClick={() => void handleSend()}
                  disabled={sendMessage.isPending || createThread.isPending || !input.trim()}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-orange-500 text-white shadow-md shadow-orange-500/20 transition hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label="Send"
                >
                  {sendMessage.isPending || createThread.isPending ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <SendHorizontal className="h-5 w-5" strokeWidth={1.75} />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}
