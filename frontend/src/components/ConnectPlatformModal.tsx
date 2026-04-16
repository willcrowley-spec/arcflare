import { useCallback, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import clsx from 'clsx'

interface PlatformEntry {
  id: string
  label: string
  description: string
  enabled: boolean
  color: string
  logo: string
}

const PLATFORMS: PlatformEntry[] = [
  {
    id: 'salesforce',
    label: 'Salesforce',
    description: 'CRM, metadata, automations, licensing',
    enabled: true,
    color: 'bg-sky-50 text-sky-700 ring-sky-200',
    logo: 'SF',
  },
  {
    id: 'hubspot',
    label: 'HubSpot',
    description: 'Marketing, sales, and service hub',
    enabled: false,
    color: 'bg-orange-50 text-orange-700 ring-orange-200',
    logo: 'HS',
  },
  {
    id: 'netsuite',
    label: 'NetSuite',
    description: 'ERP, financials, and operations',
    enabled: false,
    color: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    logo: 'NS',
  },
  {
    id: 'mulesoft',
    label: 'MuleSoft',
    description: 'Integration and API management',
    enabled: false,
    color: 'bg-violet-50 text-violet-700 ring-violet-200',
    logo: 'MS',
  },
  {
    id: 'confluence',
    label: 'Confluence',
    description: 'Documentation and knowledge base',
    enabled: false,
    color: 'bg-blue-50 text-blue-700 ring-blue-200',
    logo: 'CF',
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

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose],
  )

  useEffect(() => {
    if (!open) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, handleKeyDown])

  if (!open) return null

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose()
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-semibold text-navy-900">Connect a Platform</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="divide-y divide-slate-100 px-2 py-2">
          {PLATFORMS.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={!p.enabled || connecting}
              onClick={() => p.enabled && onSelectPlatform(p.id)}
              className={clsx(
                'flex w-full items-center gap-4 rounded-xl px-4 py-3.5 text-left transition-colors',
                p.enabled
                  ? 'hover:bg-slate-50 active:bg-slate-100'
                  : 'cursor-not-allowed opacity-50',
              )}
            >
              <span
                className={clsx(
                  'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg text-xs font-bold ring-1 ring-inset',
                  p.color,
                )}
              >
                {p.logo}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-900">{p.label}</p>
                <p className="text-xs text-slate-500">{p.description}</p>
              </div>
              {p.enabled ? (
                <svg className="h-5 w-5 flex-shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              ) : (
                <span className="flex-shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Coming soon
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="border-t border-slate-100 px-6 py-3">
          <p className="text-center text-xs text-slate-400">
            Additional platforms will be available in future releases.
          </p>
        </div>
      </div>
    </div>
  )
}
