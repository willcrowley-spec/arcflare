import { useCallback, useEffect, useRef } from 'react'
import { Info, X } from 'lucide-react'
import { SyncEventLogPanel } from './SyncEventLogPanel'
import type { SyncEvent } from '@/types'
import type { SyncStreamStatus } from '@/hooks/useSyncEventStream'

interface Props {
  open: boolean
  onClose: () => void
  events: SyncEvent[]
  streamStatus: SyncStreamStatus
  platformLabel?: string
}

export function SyncProgressModal({ open, onClose, events, streamStatus, platformLabel }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )
        if (!focusable.length) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    },
    [onClose],
  )

  useEffect(() => {
    if (!open) return
    document.addEventListener('keydown', handleKeyDown)
    const prev = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      prev?.focus()
    }
  }, [open, handleKeyDown])

  if (!open) return null

  const isTerminal = streamStatus === 'completed' || streamStatus === 'failed'

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sync-progress-title"
        className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 id="sync-progress-title" className="text-lg font-semibold text-navy-900">
            {platformLabel ? `Syncing ${platformLabel}` : 'Sync Progress'}
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 py-5">
          <SyncEventLogPanel events={events} status={streamStatus} />
        </div>

        <div className="flex items-start gap-2.5 border-t border-slate-100 px-6 py-3.5">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
          <p className="text-xs leading-relaxed text-slate-500">
            {isTerminal
              ? 'Sync has finished. You can close this window.'
              : 'This sync runs in the background. You can close this window and continue working \u2014 progress is also visible on the platform detail page.'}
          </p>
        </div>
      </div>
    </div>
  )
}
