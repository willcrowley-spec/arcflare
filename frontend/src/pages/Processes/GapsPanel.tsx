import { useMemo, useState } from 'react'
import { ArrowRight, ChevronDown, Loader2, MessageSquareText, Undo2 } from 'lucide-react'
import clsx from 'clsx'
import { useGaps, useUpdateGap } from '@/hooks/useChat'
import { useChatStore } from '@/stores/chatStore'
import type { GapItem } from '@/types'

function confidenceTone(score: number): { className: string; label: string } {
  if (score > 0.7) return { className: 'bg-emerald-100 text-emerald-800 ring-emerald-200/80', label: 'Higher confidence' }
  if (score >= 0.5) return { className: 'bg-amber-100 text-amber-900 ring-amber-200/80', label: 'Medium confidence' }
  return { className: 'bg-red-100 text-red-800 ring-red-200/80', label: 'Lower confidence' }
}

function statusPill(status: GapItem['gap_status']) {
  if (status === 'resolved') {
    return (
      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-200/80">
        Resolved
      </span>
    )
  }
  if (status === 'investigating') {
    return (
      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-900 ring-1 ring-amber-200/80">
        Investigating
      </span>
    )
  }
  return (
    <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-800 ring-1 ring-red-200/80">
      Open
    </span>
  )
}

function buildGapPrompt(g: GapItem): string {
  const src = g.source_process_name ?? 'Unknown'
  const tgt = g.target_process_name ?? 'Unknown'
  const srcDom = g.source_domain_name ?? 'Unknown domain'
  const tgtDom = g.target_domain_name ?? 'Unknown domain'
  const desc = g.description ? `\n\nDescription: "${g.description}"` : ''
  return (
    `I'm looking at a cross-domain gap between "${src}" (${srcDom}) and "${tgt}" (${tgtDom}). ` +
    `Confidence is ${Math.round(g.confidence_score * 100)}%.${desc}\n\n` +
    `Can you help me document what currently happens at this handoff point?`
  )
}

export function GapsPanel() {
  const { data: gaps = [], isLoading, isError, refetch } = useGaps()
  const updateGap = useUpdateGap()
  const openContextualChat = useChatStore((s) => s.openContextualChat)
  const dismissedGaps = useChatStore((s) => s.dismissedGaps)
  const dismissGap = useChatStore((s) => s.dismissGap)
  const undoGapDismiss = useChatStore((s) => s.undoGapDismiss)

  const openGaps = gaps.filter((g) => g.gap_status !== 'resolved')
  const visibleGaps = useMemo(() => {
    return openGaps.filter((g) => !dismissedGaps.has(g.id))
  }, [openGaps, dismissedGaps])
  const pendingDismissals = useMemo(() => {
    return openGaps.filter((g) => dismissedGaps.has(g.id))
  }, [openGaps, dismissedGaps])

  const count = visibleGaps.length

  const [expandOverride, setExpandOverride] = useState<boolean | undefined>(undefined)
  const expanded = expandOverride ?? count > 0
  const [showAll, setShowAll] = useState(false)

  const displayGaps = useMemo(() => {
    if (showAll || visibleGaps.length <= 5) return visibleGaps
    return visibleGaps.slice(0, 3)
  }, [visibleGaps, showAll])

  const handleDismiss = (g: GapItem) => {
    dismissGap(g.id)
    setTimeout(() => {
      const stillDismissed = useChatStore.getState().dismissedGaps.has(g.id)
      if (stillDismissed) {
        updateGap.mutate({
          id: g.id,
          data: { gap_status: 'resolved', resolution_note: 'Dismissed from Processes page' },
        })
      }
    }, 5200)
  }

  const header = (
    <button
      type="button"
      onClick={() =>
        setExpandOverride((prev) => {
          const cur = prev ?? count > 0
          return !cur
        })
      }
      className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-white px-4 py-3 text-left shadow-sm ring-1 ring-slate-900/5 transition hover:bg-slate-50/80"
    >
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy-800 text-white shadow-sm">
          <MessageSquareText className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <div>
          <p className="text-sm font-semibold text-navy-900">Cross-Domain Gaps</p>
          <p className="text-xs text-slate-500">
            {count === 0 ? 'No cross-domain gaps identified' : `${count} gap${count === 1 ? '' : 's'} need attention`}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {count > 0 ? (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-800 ring-1 ring-red-200/80">
            {count}
          </span>
        ) : null}
        <ChevronDown
          className={clsx('h-5 w-5 text-slate-400 transition-transform', expanded && 'rotate-180')}
          aria-hidden
        />
      </div>
    </button>
  )

  if (isLoading) {
    return (
      <div className="space-y-2">
        {header}
        {expanded ? (
          <div className="flex items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white py-10">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        ) : null}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="space-y-2">
        {header}
        {expanded ? (
          <div className="rounded-xl border border-red-200 bg-red-50/50 px-4 py-3 text-sm text-red-800">
            <p className="font-medium">Could not load gaps.</p>
            <button
              type="button"
              onClick={() => void refetch()}
              className="mt-2 text-xs font-semibold text-red-900 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {header}

      {expanded && count === 0 && pendingDismissals.length === 0 ? (
        <p className="px-1 text-xs text-slate-500">No cross-domain gaps identified.</p>
      ) : null}

      {expanded && (count > 0 || pendingDismissals.length > 0) ? (
        <>
          {pendingDismissals.length > 0 ? (
            <div className="space-y-2">
              {pendingDismissals.map((g) => (
                <div
                  key={g.id}
                  className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50/80 px-4 py-2.5 text-sm"
                >
                  <span className="text-amber-900">
                    Gap dismissed: <span className="font-semibold">{g.source_process_name} → {g.target_process_name}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => undoGapDismiss(g.id)}
                    className="ml-3 inline-flex shrink-0 items-center gap-1 rounded-md bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900 ring-1 ring-amber-300/80 transition hover:bg-amber-200"
                  >
                    <Undo2 className="h-3.5 w-3.5" />
                    Undo
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            {displayGaps.map((g) => {
              const tone = confidenceTone(g.confidence_score)
              const srcDomain = g.source_domain_name ?? 'Unknown domain'
              const tgtDomain = g.target_domain_name ?? 'Unknown domain'
              return (
                <article
                  key={g.id}
                  className="flex flex-col rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm ring-1 ring-slate-900/5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-bold text-navy-900">{srcDomain}</span>
                    <ArrowRight className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
                    <span className="text-sm font-bold text-navy-900">{tgtDomain}</span>
                  </div>
                  <p className="mt-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                    {g.source_process_name} → {g.target_process_name}
                  </p>
                  {g.description ? (
                    <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-slate-600">{g.description}</p>
                  ) : (
                    <p className="mt-2 text-sm italic text-slate-400">No description</p>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span
                      className={clsx(
                        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1',
                        tone.className,
                      )}
                      title={tone.label}
                    >
                      {Math.round(g.confidence_score * 100)}% confidence
                    </span>
                    {statusPill(g.gap_status)}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        openContextualChat({ type: 'gap', id: g.id }, buildGapPrompt(g))
                      }}
                      className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-orange-500 px-3 py-2 text-sm font-semibold text-white shadow-sm shadow-orange-500/20 transition hover:bg-orange-400 sm:flex-none"
                    >
                      <MessageSquareText className="h-4 w-4" />
                      Chat with AI
                    </button>
                    <button
                      type="button"
                      disabled={updateGap.isPending}
                      onClick={() => handleDismiss(g)}
                      className="inline-flex flex-1 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 sm:flex-none"
                    >
                      Dismiss
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
          {visibleGaps.length > 5 && !showAll ? (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="w-full rounded-lg border border-slate-200 bg-white py-2 text-sm font-semibold text-navy-900 shadow-sm ring-1 ring-slate-900/5 transition hover:bg-slate-50"
            >
              Show all {visibleGaps.length} gaps
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
