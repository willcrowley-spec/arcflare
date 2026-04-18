import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import type { CardOption } from '@/types'
import { useTypewriter } from '@/hooks/useTypewriter'

function RevealingCard({
  option,
  animate,
  onDone,
  disabled,
  isSelected,
  isSubmitted,
  onSelect,
}: {
  option: CardOption
  animate: boolean
  onDone?: () => void
  disabled: boolean
  isSelected: boolean
  isSubmitted: boolean
  onSelect: () => void
}) {
  const { displayed, done } = useTypewriter(option.label, animate)
  const firedRef = useRef(false)

  useEffect(() => {
    if (done && animate && onDone && !firedRef.current) {
      firedRef.current = true
      onDone()
    }
  }, [done, animate, onDone])

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={clsx(
        'flex w-full flex-col rounded-lg border p-3 text-left transition animate-[fade-in_200ms_ease-out]',
        isSelected
          ? 'border-orange-300 bg-orange-50 ring-1 ring-orange-200'
          : isSubmitted
            ? 'border-slate-100 bg-slate-50 opacity-60'
            : 'border-slate-200 bg-white hover:border-orange-200 hover:bg-orange-50/50',
      )}
    >
      <span className="text-sm font-semibold text-slate-800">
        <span className="mr-1.5 text-slate-400">{option.id.toUpperCase()}.</span>
        {animate && !done ? displayed : option.label}
      </span>
      <span
        className={clsx(
          'mt-0.5 text-xs leading-relaxed text-slate-500 transition-opacity duration-300',
          animate && !done ? 'opacity-0' : 'opacity-100',
        )}
      >
        {option.description}
      </span>
    </button>
  )
}

interface OptionCardGroupProps {
  options: CardOption[]
  onSelect: (option: CardOption) => void
  /** When set, cards render sequentially up to this index with typewriter. */
  revealUpTo?: number
  /** Fires when the current card's typewriter finishes. */
  onOptionRevealed?: () => void
}

export function OptionCardGroup({ options, onSelect, revealUpTo, onOptionRevealed }: OptionCardGroupProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const showAll = revealUpTo === undefined
  const allRevealed = showAll || (revealUpTo ?? -1) >= options.length

  return (
    <div className="mt-2 space-y-2 px-2">
      {options.map((opt, i) => {
        if (!showAll && i > (revealUpTo ?? -1)) return null
        const isRevealing = !showAll && i === revealUpTo
        return (
          <RevealingCard
            key={opt.id}
            option={opt}
            animate={isRevealing}
            onDone={isRevealing ? onOptionRevealed : undefined}
            disabled={submitted}
            isSelected={selected === opt.id}
            isSubmitted={submitted}
            onSelect={() => setSelected(opt.id)}
          />
        )
      })}
      {selected && !submitted && allRevealed ? (
        <button
          type="button"
          onClick={() => {
            setSubmitted(true)
            const opt = options.find((o) => o.id === selected)
            if (opt) onSelect(opt)
          }}
          className="w-full rounded-lg bg-orange-500 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-orange-400 animate-[fade-in_200ms_ease-out]"
        >
          Continue
        </button>
      ) : null}
    </div>
  )
}
