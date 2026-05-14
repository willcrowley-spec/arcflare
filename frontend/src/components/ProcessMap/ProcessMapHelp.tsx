import { Info } from 'lucide-react'
import clsx from 'clsx'

type Align = 'start' | 'center' | 'end'

export function InfoHint({
  text,
  className,
  align = 'start',
}: {
  text: string
  className?: string
  align?: Align
}) {
  const positionClass =
    align === 'end' ? 'right-0'
    : align === 'center' ? 'left-1/2 -translate-x-1/2'
    : 'left-0'

  return (
    <span
      tabIndex={0}
      aria-label={text}
      className={clsx(
        'group/help relative inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 outline-none hover:text-navy-700 focus-visible:text-navy-700',
        className,
      )}
    >
      <Info className="h-3.5 w-3.5" aria-hidden />
      <span
        role="tooltip"
        className={clsx(
          'pointer-events-none absolute top-full z-50 mt-2 hidden w-72 max-w-[calc(100vw-2rem)] rounded-md bg-navy-900 px-3 py-2 text-left text-xs font-medium leading-relaxed text-white shadow-lg group-hover/help:block group-focus/help:block',
          positionClass,
        )}
      >
        {text}
      </span>
    </span>
  )
}

export const VALUE_CLASSIFICATION_HELP: Record<string, string> = {
  VA: 'Value-adding. This work directly creates customer, revenue, delivery, or product value.',
  BVA: 'Business-necessary. This work is required to run, control, coordinate, or govern the business, but it may not directly create customer value.',
  NVA: 'Non-value-added. This usually means avoidable admin, waiting, rework, duplication, or handoff friction.',
}

export function valueClassificationHelp(value?: string | null) {
  if (!value) return null
  return VALUE_CLASSIFICATION_HELP[value.toUpperCase()] ?? 'Value classification for this process step.'
}

export function automationPotentialHelp(value?: string | null) {
  if (!value) return null
  const label = value.toLowerCase()
  if (label === 'high') {
    return 'High automation potential means the process appears repetitive, bounded, evidence-backed, and suitable for automation or agent assistance.'
  }
  if (label === 'medium') {
    return 'Medium automation potential means there may be useful automation, but scope, evidence, risk, or human judgment needs review.'
  }
  if (label === 'low') {
    return 'Low automation potential means the process likely needs human judgment, stronger evidence, or redesign before automation is useful.'
  }
  return 'Automation potential is an analyst signal, not an implementation approval.'
}
