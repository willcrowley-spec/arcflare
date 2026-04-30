import { useCallback, useEffect, useRef } from 'react'
import { ChevronRight, X } from 'lucide-react'
import clsx from 'clsx'

interface PlatformEntry {
  id: string
  label: string
  description: string
  logo: string
}

const PLATFORMS: PlatformEntry[] = [
  {
    id: 'salesforce',
    label: 'Salesforce',
    description: 'CRM metadata, automations, licensing, and org health',
    logo: 'SF',
  },
]

interface Props {
  open: boolean
  onClose: () => void
  onSelectPlatform: (platformId: string) => void
  connecting?: boolean
}

export function ConnectPlatformModal({ open, onClose, onSelectPlatform, connecting }: Props) {
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

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/55 px-4"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="connect-platform-title"
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white shadow-xl shadow-navy-900/15"
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 id="connect-platform-title" className="text-lg font-semibold text-navy-900">
            Connect Salesforce
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

        <div className="divide-y divide-slate-100 px-2 py-2">
          {PLATFORMS.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={connecting}
              onClick={() => onSelectPlatform(p.id)}
              className={clsx(
                'flex w-full items-center gap-4 rounded-lg px-4 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-200',
                connecting ? 'cursor-wait opacity-70' : 'hover:bg-slate-50 active:bg-slate-100',
              )}
            >
              <span
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-navy-50 text-xs font-bold text-navy-800 ring-1 ring-inset ring-navy-200"
              >
                {p.logo}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-900">{p.label}</p>
                <p className="text-xs text-slate-500">{p.description}</p>
              </div>
              <ChevronRight className="h-5 w-5 flex-shrink-0 text-slate-400" />
            </button>
          ))}
        </div>

        <div className="border-t border-slate-100 px-6 py-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Arcflare will redirect you to Salesforce to review permissions before the connection is saved.
          </p>
        </div>
      </div>
    </div>
  )
}
