import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  List,
  Loader2,
  MessageSquareText,
  Plus,
  SendHorizontal,
  Sparkles,
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
import type { ArcResponse, ChatAction, ChatMessage as ChatMessageRow } from '@/types'
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
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const [streamingActions, setStreamingActions] = useState<StreamAction[]>([])
  const [sendError, setSendError] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const didSendInitialRef = useRef(false)

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [])

  const autoGrow = useCallback(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`
  }, [])

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

  useEffect(() => { scrollToBottom() }, [streamingText, detail?.messages, scrollToBottom])

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
        <div className="flex items-center gap-0.5">
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
                onClick={() => { setThreadMenu(false); setConfirmDeleteId(null) }}
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
                          confirmDeleteId === t.id
                            ? 'bg-red-50'
                            : t.id === activeThreadId
                              ? 'bg-orange-50 text-orange-800'
                              : 'hover:bg-slate-50',
                        )}
                      >
                        {confirmDeleteId === t.id ? (
                          <div className="flex w-full items-center justify-between gap-2">
                            <p className="truncate text-xs font-medium text-red-700">Delete?</p>
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setConfirmDeleteId(null)
                                  void handleDeleteThread(t.id)
                                }}
                                className="rounded px-2 py-0.5 text-[11px] font-semibold text-red-600 transition hover:bg-red-100"
                              >
                                Yes
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setConfirmDeleteId(null)
                                }}
                                className="rounded px-2 py-0.5 text-[11px] font-semibold text-slate-500 transition hover:bg-slate-100"
                              >
                                No
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setActiveThread(t.id)
                                setThreadMenu(false)
                                setConfirmDeleteId(null)
                              }}
                              className="min-w-0 flex-1 text-left"
                            >
                              <p className="truncate text-xs font-medium">{t.title || 'Untitled'}</p>
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                setConfirmDeleteId(t.id)
                              }}
                              className="shrink-0 rounded p-0.5 text-slate-400 opacity-0 transition hover:text-red-500 group-hover:opacity-100"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : null}
          </div>
          <button
            type="button"
            onClick={closeChat}
            className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close chat"
          >
            <X className="h-4 w-4" />
          </button>
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
              sortedMessages.map((m: ChatMessageRow, idx: number) => (
                <div key={m.id}>
                  <ChatMessage
                    message={m}
                    onQuickReply={handleQuickReply}
                    animate={m.role === 'assistant' && idx === sortedMessages.length - 1 && !streamingText}
                    onTick={m.role === 'assistant' && idx === sortedMessages.length - 1 ? scrollToBottom : undefined}
                  />
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

            {streamingText ? (() => {
              let parsed: ArcResponse | null = null
              try {
                const obj = JSON.parse(streamingText)
                if (obj && typeof obj === 'object' && 'type' in obj) parsed = obj as ArcResponse
              } catch { /* partial JSON — not parseable yet */ }

              const displayText = parsed?.text
              if (!displayText) return null

              return (
                <div className="group flex justify-start px-2 py-1.5">
                  <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2 text-sm leading-relaxed text-slate-800 shadow-sm">
                    <p className="whitespace-pre-wrap break-words">{displayText}</p>
                    <span className="mt-1 inline-flex items-center gap-1 text-[10px] text-orange-500">
                      <Loader2 className="h-2.5 w-2.5 animate-spin" /> Generating
                    </span>
                  </div>
                </div>
              )
            })() : null}

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
            disabled={!!streamingText || sendMessage.isPending}
            onChange={(e) => { setInput(e.target.value); autoGrow() }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void handleSend()
              }
            }}
            rows={1}
            placeholder={streamingText ? `${agentName} is responding…` : `Message ${agentName}…`}
            className={clsx(
              'min-h-[44px] max-h-32 flex-1 resize-none rounded-xl border px-3.5 py-2.5 text-[15px] leading-snug text-slate-800 shadow-inner shadow-slate-900/5 placeholder:text-slate-400 focus:border-orange-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-400/20',
              streamingText || sendMessage.isPending
                ? 'border-slate-100 bg-slate-50 opacity-60 cursor-not-allowed'
                : 'border-slate-200 bg-slate-50/80',
            )}
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={sendMessage.isPending || createThread.isPending || !input.trim() || !!streamingText}
            className="inline-flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-xl bg-orange-500 text-white shadow-sm transition hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-40"
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
