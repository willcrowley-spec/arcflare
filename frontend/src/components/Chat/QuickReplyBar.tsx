import { useState } from 'react'
import type { QuickOption } from '@/types'

interface QuickReplyBarProps {
  options: QuickOption[]
  onSelect: (option: QuickOption) => void
  stagger?: boolean
}

export function QuickReplyBar({ options, onSelect, stagger }: QuickReplyBarProps) {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <div className="mt-2 flex flex-col gap-1.5 px-2">
      {options.map((opt, i) => (
        <button
          key={opt.id}
          type="button"
          disabled={selected !== null}
          onClick={() => {
            setSelected(opt.id)
            onSelect(opt)
          }}
          className={
            'w-fit rounded-full border px-3 py-1.5 text-left text-xs font-medium transition ' +
            (stagger ? 'animate-[fade-in_250ms_ease-out_both] ' : '') +
            (selected === opt.id
              ? 'border-orange-300 bg-orange-50 text-orange-800'
              : selected !== null
                ? 'border-slate-100 bg-slate-50 text-slate-400 cursor-default'
                : 'border-slate-200 bg-white text-slate-700 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-800')
          }
          style={stagger ? { animationDelay: `${i * 80}ms` } : undefined}
        >
          <span className="mr-1.5 font-semibold text-slate-400">{opt.id.toUpperCase()}</span>
          {opt.label}
        </button>
      ))}
    </div>
  )
}
