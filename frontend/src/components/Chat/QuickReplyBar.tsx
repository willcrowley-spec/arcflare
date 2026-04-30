import { useEffect, useRef, useState } from 'react'
import type { QuickOption } from '@/types'
import { useTypewriter } from '@/hooks/useTypewriter'

function RevealingReply({
  option,
  animate,
  onDone,
  disabled,
  isSelected,
  isDimmed,
  onSelect,
}: {
  option: QuickOption
  animate: boolean
  onDone?: () => void
  disabled: boolean
  isSelected: boolean
  isDimmed: boolean
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
      className={
        'w-fit rounded-full border px-3 py-1.5 text-left text-xs font-medium transition animate-[fade-in_200ms_ease-out] ' +
        (isSelected
          ? 'border-orange-300 bg-orange-50 text-orange-900'
          : isDimmed
            ? 'border-slate-100 bg-slate-50 text-slate-400 cursor-default'
            : 'border-slate-200 bg-white text-navy-800 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-900')
      }
    >
      <span className="mr-1.5 font-semibold opacity-70">{option.id.toUpperCase()}</span>
      {animate && !done ? displayed : option.label}
    </button>
  )
}

interface QuickReplyBarProps {
  options: QuickOption[]
  onSelect: (option: QuickOption) => void
  /** When set, options render sequentially up to this index with typewriter. */
  revealUpTo?: number
  /** Fires when the current option's typewriter finishes. */
  onOptionRevealed?: () => void
}

export function QuickReplyBar({ options, onSelect, revealUpTo, onOptionRevealed }: QuickReplyBarProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const showAll = revealUpTo === undefined

  return (
    <div className="mt-2 flex flex-col gap-1.5 px-2">
      {options.map((opt, i) => {
        if (!showAll && i > (revealUpTo ?? -1)) return null
        const isRevealing = !showAll && i === revealUpTo
        return (
          <RevealingReply
            key={opt.id}
            option={opt}
            animate={isRevealing}
            onDone={isRevealing ? onOptionRevealed : undefined}
            disabled={selected !== null}
            isSelected={selected === opt.id}
            isDimmed={selected !== null && selected !== opt.id}
            onSelect={() => {
              setSelected(opt.id)
              onSelect(opt)
            }}
          />
        )
      })}
    </div>
  )
}
