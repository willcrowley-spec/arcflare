import { ArrowRight, ArrowDown, Maximize2, Minimize2, RotateCcw } from 'lucide-react'
import clsx from 'clsx'

interface MapToolbarProps {
  direction: 'LR' | 'TB'
  onDirectionChange: (dir: 'LR' | 'TB') => void
  onExpandAll: () => void
  onCollapseAll: () => void
  onResetLayout: () => void
}

export function MapToolbar({
  direction,
  onDirectionChange,
  onExpandAll,
  onCollapseAll,
  onResetLayout,
}: MapToolbarProps) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1.5 shadow-sm">
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

      <div className="mx-1 h-4 w-px bg-slate-200" />

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

      <div className="mx-1 h-4 w-px bg-slate-200" />

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
