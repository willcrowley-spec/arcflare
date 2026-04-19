import { useCallback, useEffect, useRef, useState } from 'react'
import type { SyncEvent } from '@/types'

export type SyncStreamStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed'

export function useSyncEventStream(connectionId: string | null) {
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

    setStatus('connecting')

    return () => {
      close()
    }
  }, [connectionId, close])

  const reset = useCallback(() => {
    close()
    setEvents([])
    setStatus('idle')
  }, [close])

  return { events, status, reset }
}
