import { useCallback, useEffect, useRef } from 'react'
import { ExternalLink, ShieldCheck, X } from 'lucide-react'
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

const SALESFORCE_CONNECTOR_VERSION = '1.0.0.2'
const SALESFORCE_PACKAGE_VERSION_ID = '04tUp000001HpyPIAS'
const SALESFORCE_PROD_INSTALL_URL = `https://login.salesforce.com/packaging/installPackage.apexp?p0=${SALESFORCE_PACKAGE_VERSION_ID}`
const SALESFORCE_SANDBOX_INSTALL_URL = `https://test.salesforce.com/packaging/installPackage.apexp?p0=${SALESFORCE_PACKAGE_VERSION_ID}`

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
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
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

        <div className="px-6 py-5">
          {PLATFORMS.map((p) => (
            <div key={p.id} className="space-y-5">
              <div className="flex items-start gap-4">
                <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-navy-50 text-xs font-bold text-navy-800 ring-1 ring-inset ring-navy-200">
                  {p.logo}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-900">{p.label}</p>
                  <p className="text-xs leading-5 text-slate-500">{p.description}</p>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-navy-700" aria-hidden />
                  <div>
                    <p className="text-sm font-medium text-slate-900">Install connector first</p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">
                      Required once per Salesforce org before Arcflare can complete OAuth authorization.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                <a
                  href={SALESFORCE_PROD_INSTALL_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-navy-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-200"
                >
                  Production
                  <ExternalLink className="h-4 w-4" aria-hidden />
                </a>
                <a
                  href={SALESFORCE_SANDBOX_INSTALL_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-navy-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-200"
                >
                  Sandbox
                  <ExternalLink className="h-4 w-4" aria-hidden />
                </a>
              </div>

              <button
                type="button"
                disabled={connecting}
                onClick={() => onSelectPlatform(p.id)}
                className={clsx(
                  'inline-flex w-full min-h-10 items-center justify-center gap-2 rounded-lg bg-navy-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm ring-1 ring-navy-900/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-200',
                  connecting ? 'cursor-wait opacity-70' : 'hover:bg-navy-800 active:bg-navy-900',
                )}
              >
                {connecting ? 'Starting authorization...' : 'Continue to Salesforce authorization'}
              </button>
            </div>
          ))}
        </div>

        <div className="border-t border-slate-100 px-6 py-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Connector package {SALESFORCE_CONNECTOR_VERSION}. Return here after install to authorize access.
          </p>
        </div>
      </div>
    </div>
  )
}
