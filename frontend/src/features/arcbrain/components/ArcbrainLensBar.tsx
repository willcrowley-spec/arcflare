import clsx from 'clsx'
import { BrainCircuit, CircleDollarSign, Radar, ShieldCheck } from 'lucide-react'
import type { ArcbrainLens } from '@/types'
import { formatDateTime, type ArcbrainGraphModel } from '@/features/arcbrain/graph/model'
import { ArcbrainStatusPill } from './ArcbrainHeader'

const LENSES: Array<{ id: ArcbrainLens; label: string; icon: typeof BrainCircuit }> = [
  { id: 'overview', label: 'Overview', icon: BrainCircuit },
  { id: 'replacement_heat', label: 'Replacement Heat', icon: CircleDollarSign },
  { id: 'blast_radius', label: 'Blast Radius', icon: Radar },
  { id: 'trust', label: 'Trust', icon: ShieldCheck },
]

interface ArcbrainLensBarProps {
  lens: ArcbrainLens
  onLensChange: (lens: ArcbrainLens) => void
  summary: ArcbrainGraphModel['summary']
}

export function ArcbrainLensBar({ lens, onLensChange, summary }: ArcbrainLensBarProps) {
  return (
    <section className="grid w-full max-w-full min-w-0 gap-4 overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5 lg:grid-cols-[1fr_auto] lg:items-center">
      <div className="flex min-w-0 flex-wrap gap-2" role="tablist" aria-label="Arcbrain lens">
        {LENSES.map((item) => {
          const Icon = item.icon
          const active = lens === item.id
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onLensChange(item.id)}
              className={clsx(
                'inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold ring-1 ring-inset transition-colors',
                active
                  ? 'bg-navy-800 text-white ring-navy-800'
                  : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          )
        })}
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-3 text-xs text-slate-500">
        <ArcbrainStatusPill label="Projection" value={summary.projection_status ?? 'ready'} />
        <ArcbrainStatusPill label="Staleness" value={summary.staleness_status ?? 'unknown'} />
        <span>Generated {formatDateTime(summary.generated_at)}</span>
      </div>
    </section>
  )
}
