import { ArrowRight, ArrowDown, Bot, FileSearch, GitBranch, Maximize2, Minimize2, RotateCcw, Search, Workflow } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import clsx from 'clsx'
import type { ProcessMapLens } from '@/types'

interface MapToolbarProps {
  direction: 'LR' | 'TB'
  lens: ProcessMapLens
  searchQuery: string
  searchResultCount: number
  onDirectionChange: (dir: 'LR' | 'TB') => void
  onLensChange: (lens: ProcessMapLens) => void
  onSearchQueryChange: (query: string) => void
  onSearchSubmit: () => void
  onExpandAll: () => void
  onCollapseAll: () => void
  onResetLayout: () => void
}

const lenses: Array<{ id: ProcessMapLens; label: string; icon: LucideIcon }> = [
  { id: 'structure', label: 'Structure', icon: Workflow },
  { id: 'handoffs', label: 'Handoffs', icon: GitBranch },
  { id: 'evidence', label: 'Evidence', icon: FileSearch },
  { id: 'automation', label: 'Automation', icon: Bot },
]

export function MapToolbar({
  direction,
  lens,
  searchQuery,
  searchResultCount,
  onDirectionChange,
  onLensChange,
  onSearchQueryChange,
  onSearchSubmit,
  onExpandAll,
  onCollapseAll,
  onResetLayout,
}: MapToolbarProps) {
  return (
    <div className="flex max-w-[calc(100vw-3rem)] flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5 shadow-sm">
      <div className="flex rounded-md bg-slate-100 p-0.5">
        {lenses.map((item) => {
          const Icon = item.icon
          const active = lens === item.id
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onLensChange(item.id)}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold transition',
                active ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-slate-800',
              )}
              title={`${item.label} lens`}
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
            </button>
          )
        })}
      </div>

      <form
        className="relative"
        onSubmit={(event) => {
          event.preventDefault()
          onSearchSubmit()
        }}
      >
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
        <input
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          placeholder="Search process, actor, system"
          className="h-7 w-64 rounded-md border border-slate-200 bg-white pl-7 pr-16 text-xs font-medium text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-navy-300 focus:ring-2 focus:ring-navy-100"
        />
        <button
          type="submit"
          className="absolute right-1 top-1/2 -translate-y-1/2 rounded px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        >
          {searchQuery.trim() ? `${searchResultCount}` : 'Find'}
        </button>
      </form>

      <div className="h-4 w-px bg-slate-200" />

      <button
        type="button"
        onClick={() => onDirectionChange(direction === 'LR' ? 'TB' : 'LR')}
        className={clsx(
          'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition',
          'text-slate-600 hover:bg-slate-50 hover:text-slate-800',
        )}
        title={`Switch to ${direction === 'LR' ? 'top-to-bottom' : 'left-to-right'} layout`}
      >
        {direction === 'LR' ? <ArrowRight className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
        {direction === 'LR' ? 'LR' : 'TB'}
      </button>

      <div className="h-4 w-px bg-slate-200" />

      <button
        type="button"
        onClick={onExpandAll}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-800"
        title="Expand all containers"
      >
        <Maximize2 className="h-3 w-3" />
        Expand
      </button>

      <button
        type="button"
        onClick={onCollapseAll}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-800"
        title="Collapse all containers"
      >
        <Minimize2 className="h-3 w-3" />
        Collapse
      </button>

      <div className="h-4 w-px bg-slate-200" />

      <button
        type="button"
        onClick={onResetLayout}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-800"
        title="Reset layout to auto-computed positions"
      >
        <RotateCcw className="h-3 w-3" />
        Reset
      </button>
    </div>
  )
}
