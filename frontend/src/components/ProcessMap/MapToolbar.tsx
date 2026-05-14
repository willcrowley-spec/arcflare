import { ArrowRight, ArrowDown, Bot, FileSearch, GitBranch, Maximize2, Minimize2, RotateCcw, Search, Workflow } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import clsx from 'clsx'
import type { ProcessMapLens } from '@/types'
import { InfoHint } from './ProcessMapHelp'

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

const lenses: Array<{ id: ProcessMapLens; label: string; icon: LucideIcon; summary: string; help: string }> = [
  {
    id: 'structure',
    label: 'Structure',
    icon: Workflow,
    summary: 'Showing the full visible hierarchy.',
    help: 'Structure is the default map view. It keeps all visible process steps and sequence links at normal emphasis.',
  },
  {
    id: 'handoffs',
    label: 'Handoffs',
    icon: GitBranch,
    summary: 'Highlighting handoffs and gaps.',
    help: 'Handoffs highlights cross-process handoffs and gaps. Routine sequence links fade back so transfer points are easier to inspect.',
  },
  {
    id: 'evidence',
    label: 'Evidence',
    icon: FileSearch,
    summary: 'Highlighting items with source evidence.',
    help: 'Evidence highlights process steps and links with captured source artifacts. Items without linked evidence fade back.',
  },
  {
    id: 'automation',
    label: 'Automation',
    icon: Bot,
    summary: 'Highlighting automation candidates.',
    help: 'Automation highlights processes with medium or high automation potential. Handoff lines fade back so the candidate process steps stand out.',
  },
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
  const activeLens = lenses.find((item) => item.id === lens) ?? lenses[0]

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
              aria-pressed={active}
              aria-label={`${item.label} lens. ${item.help}`}
              onClick={() => onLensChange(item.id)}
              className={clsx(
                'group/lens relative inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold transition',
                active ? 'bg-white text-navy-900 shadow-sm ring-1 ring-orange-200' : 'text-slate-500 hover:bg-white/70 hover:text-slate-800',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
              <span className="pointer-events-none absolute left-0 top-full z-50 mt-2 hidden w-72 rounded-md bg-navy-900 px-3 py-2 text-left text-xs font-medium leading-relaxed text-white shadow-lg group-hover/lens:block group-focus-visible/lens:block">
                {item.help}
              </span>
            </button>
          )
        })}
      </div>

      <div className="hidden max-w-[20rem] items-center gap-1.5 px-1 text-[11px] font-medium leading-snug text-slate-500 lg:flex">
        <InfoHint text={activeLens.help} align="start" />
        <span>{activeLens.summary}</span>
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
