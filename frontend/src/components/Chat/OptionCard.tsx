import { useState } from 'react'
import clsx from 'clsx'
import type { CardOption } from '@/types'

interface OptionCardGroupProps {
  options: CardOption[]
  onSelect: (option: CardOption) => void
  stagger?: boolean
}

export function OptionCardGroup({ options, onSelect, stagger }: OptionCardGroupProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  return (
    <div className="mt-2 space-y-2 px-2">
      {options.map((opt, i) => (
        <button
          key={opt.id}
          type="button"
          disabled={submitted}
          onClick={() => setSelected(opt.id)}
          className={clsx(
            'flex w-full flex-col rounded-lg border p-3 text-left transition',
            stagger && 'animate-[fade-in_250ms_ease-out_both]',
            selected === opt.id
              ? 'border-orange-300 bg-orange-50 ring-1 ring-orange-200'
              : submitted
                ? 'border-slate-100 bg-slate-50 opacity-60'
                : 'border-slate-200 bg-white hover:border-orange-200 hover:bg-orange-50/50',
          )}
          style={stagger ? { animationDelay: `${i * 80}ms` } : undefined}
        >
          <span className="text-sm font-semibold text-slate-800">
            <span className="mr-1.5 text-slate-400">{opt.id.toUpperCase()}.</span>
            {opt.label}
          </span>
          <span className="mt-0.5 text-xs leading-relaxed text-slate-500">{opt.description}</span>
        </button>
      ))}
      {selected && !submitted ? (
        <button
          type="button"
          onClick={() => {
            setSubmitted(true)
            const opt = options.find((o) => o.id === selected)
            if (opt) onSelect(opt)
          }}
          className={clsx(
            'w-full rounded-lg bg-orange-500 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-orange-400',
            stagger && 'animate-[fade-in_250ms_ease-out_both]',
          )}
          style={stagger ? { animationDelay: `${options.length * 80}ms` } : undefined}
        >
          Continue
        </button>
      ) : null}
    </div>
  )
}
