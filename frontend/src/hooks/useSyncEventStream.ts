import { useCallback, useEffect, useRef, useState } from 'react'
import type { SyncEvent } from '@/types'
import { fetchWithAuth } from '@/api/client'

export type SyncStreamStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed'

export function useSyncEventStream(connectionId: string | null, key = 0) {
  const [events, setEvents] = useState<SyncEvent[]>([])
  const [status, setStatus] = useState<SyncStreamStatus>('idle')
  const abortRef = useRef<AbortController | null>(null)

  const close = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  useEffect(() => {
    if (!connectionId) {
      setEvents([])
      setStatus('idle')
      return
    }

    const controller = new AbortController()
    abortRef.current = controller

    setEvents([])
    setStatus('connecting')

    ;(async () => {
      try {
        const res = await fetchWithAuth(`/connections/${connectionId}/sync-stream`, {
          headers: { Accept: 'text/event-stream' },
          signal: controller.signal,
        })

        if (!res.ok || !res.body) {
          setStatus('failed')
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = ''
        let currentData = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim()
              currentData = ''
            } else if (line.startsWith('data: ')) {
              const piece = line.slice(6)
              currentData = currentData ? `${currentData}\n${piece}` : piece
            } else if (line === '' && currentEvent) {
              if (currentEvent === 'backfill') {
                try {
                  const data: SyncEvent[] = JSON.parse(currentData)
                  setEvents(data)
                  const hasComplete = data.some((ev) => ev.event_type === 'run_complete')
                  const hasError = data.some((ev) => ev.event_type === 'error' && ev.severity === 'error')
                  setStatus(hasComplete ? 'completed' : hasError ? 'failed' : 'running')
                } catch { /* skip */ }
              } else if (currentEvent === 'sync_event') {
                try {
                  const event: SyncEvent = JSON.parse(currentData)
                  setEvents((prev) => [...prev, event])
                  if (event.event_type === 'run_complete') setStatus('completed')
                  else if (event.event_type === 'error' && event.severity === 'error') setStatus('failed')
                  else setStatus('running')
                } catch { /* skip */ }
              } else if (currentEvent === 'done') {
                return
              }
              currentEvent = ''
              currentData = ''
            }
          }
        }
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          setStatus((prev) => (prev === 'running' || prev === 'connecting' ? 'failed' : prev))
        }
      }
    })()

    return () => {
      controller.abort()
      abortRef.current = null
    }
  }, [connectionId, key])

  const reset = useCallback(() => {
    close()
    setEvents([])
    setStatus('idle')
  }, [close])

  return { events, status, reset }
}
