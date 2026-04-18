import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

export interface StreamAction {
  action_id: string
  action_type: string
  target_id: string | null
  payload: Record<string, unknown>
  status: string
  cascade_info?: Record<string, unknown> | null
}

export interface StreamToolResult {
  tool: string
  result?: unknown
  error?: string
}

interface SseCallbacks {
  onDelta?: (chunk: string) => void
  onAction?: (action: StreamAction) => void
  onToolResult?: (result: StreamToolResult) => void
  onToolError?: (info: { tool: string; errors: string[] }) => void
  onStatus?: (phase: string) => void
}

function handleSseBlock(block: string, callbacks: SseCallbacks) {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  const dataRaw = dataLines.join('\n')
  let payload: unknown = dataRaw
  if (dataRaw) {
    try {
      payload = JSON.parse(dataRaw) as unknown
    } catch {
      /* keep string */
    }
  }

  if (eventName === 'text' || eventName === 'message') {
    if (typeof payload === 'object' && payload !== null && 'chunk' in payload) {
      const c = (payload as { chunk?: unknown }).chunk
      if (typeof c === 'string' && c) callbacks.onDelta?.(c)
    } else if (typeof payload === 'object' && payload !== null && 'delta' in payload) {
      const d = (payload as { delta?: unknown }).delta
      if (typeof d === 'string' && d) callbacks.onDelta?.(d)
    } else if (typeof payload === 'string' && payload) {
      callbacks.onDelta?.(payload)
    }
  }

  if (eventName === 'token' || eventName === 'chunk') {
    if (typeof payload === 'object' && payload !== null && 'text' in payload) {
      const t = (payload as { text?: unknown }).text
      if (typeof t === 'string' && t) callbacks.onDelta?.(t)
    }
  }

  if (eventName === 'action' && typeof payload === 'object' && payload !== null) {
    callbacks.onAction?.(payload as StreamAction)
  }

  if (eventName === 'tool_result' && typeof payload === 'object' && payload !== null) {
    callbacks.onToolResult?.(payload as StreamToolResult)
  }

  if (eventName === 'tool_error' && typeof payload === 'object' && payload !== null) {
    callbacks.onToolError?.(payload as { tool: string; errors: string[] })
  }

  if (eventName === 'status' && typeof payload === 'object' && payload !== null && 'phase' in payload) {
    const p = (payload as { phase?: string }).phase
    if (typeof p === 'string') callbacks.onStatus?.(p)
  }
}

/** Reads an SSE response from POST /chat/threads/:id/messages */
export async function consumeChatMessageStream(
  response: Response,
  callbacks: SseCallbacks,
): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('Response has no readable body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

    let splitAt: number
    while ((splitAt = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, splitAt)
      buffer = buffer.slice(splitAt + 2)
      if (block.trim()) handleSseBlock(block, callbacks)
    }

    if (done) {
      const tail = buffer.trim()
      if (tail) handleSseBlock(tail, callbacks)
      break
    }
  }
}

export function useThreads() {
  return useQuery({
    queryKey: ['chat', 'threads'],
    queryFn: () => api.chat.listThreads(),
  })
}

export function useThread(threadId: string | null) {
  return useQuery({
    queryKey: ['chat', 'thread', threadId],
    queryFn: () => api.chat.getThread(threadId!),
    enabled: threadId != null && threadId.length > 0,
  })
}

export function useCreateThread() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body?: {
      title?: string
      anchor_type?: string | null
      anchor_id?: string | null
      model_override?: string | null
    }) => api.chat.createThread(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['chat', 'threads'] })
    },
  })
}

export function useDeleteThread() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.chat.deleteThread(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['chat', 'threads'] })
      void qc.invalidateQueries({ queryKey: ['chat', 'thread'] })
    },
  })
}

export function useSendMessage(threadId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      content,
      onDelta,
      onAction,
      onToolResult,
      onStatus,
      signal,
      threadId: threadIdOverride,
    }: {
      content: string
      onDelta?: (chunk: string) => void
      onAction?: (action: StreamAction) => void
      onToolResult?: (result: StreamToolResult) => void
      onStatus?: (phase: string) => void
      signal?: AbortSignal
      /** Use immediately after creating a thread, before React state commits. */
      threadId?: string
    }) => {
      const id = threadIdOverride ?? threadId
      if (!id) throw new Error('No thread selected')
      const res = await api.chat.sendMessageStream(id, content, signal)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || res.statusText || `Request failed (${res.status})`)
      }
      await consumeChatMessageStream(res, { onDelta, onAction, onToolResult, onStatus })
      await qc.invalidateQueries({ queryKey: ['chat', 'thread', id] })
      await qc.invalidateQueries({ queryKey: ['chat', 'threads'] })
    },
  })
}

export function useConfirmAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ actionId, body }: { actionId: string; body?: Record<string, unknown> }) =>
      api.chat.confirmAction(actionId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['chat'] })
    },
  })
}

export function useRejectAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (actionId: string) => api.chat.rejectAction(actionId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['chat'] })
    },
  })
}

export function useGaps() {
  return useQuery({
    queryKey: ['processes', 'gaps'],
    queryFn: () => api.processes.gaps(),
  })
}

export function useUpdateGap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      api.processes.updateGap(id, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['processes', 'gaps'] })
      void qc.invalidateQueries({ queryKey: ['processes'] })
    },
  })
}
