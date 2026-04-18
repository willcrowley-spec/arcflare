import { useState } from 'react'
import type { QuickOption } from '@/types'

interface QuickReplyBarProps {
  options: QuickOption[]
  onSelect: (option: QuickOption) => void
}

export function QuickReplyBar({ options, onSelect }: QuickReplyBarProps) {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <div className="mt-2 flex flex-wrap gap-1.5 px-2">
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          disabled={selected !== null}
          onClick={() => {
            setSelected(opt.id)
            onSelect(opt)
          }}
          className={
            'rounded-full border px-3 py-1.5 text-xs font-medium transition ' +
            (selected === opt.id
              ? 'border-orange-300 bg-orange-50 text-orange-800'
              : selected !== null
                ? 'border-slate-100 bg-slate-50 text-slate-400 cursor-default'
                : 'border-slate-200 bg-white text-slate-700 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-800')
          }
        >
          <span className="mr-1 font-semibold text-slate-400">{opt.id.toUpperCase()}</span>
          {opt.label}
        </button>
      ))}
    </div>
  )
}
