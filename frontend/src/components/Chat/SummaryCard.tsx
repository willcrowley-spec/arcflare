import { CheckCircle2, ArrowRight } from 'lucide-react'

interface SummaryCardProps {
  text: string
  findings: string[]
  nextSteps: string[]
}

export function SummaryCard({ text, findings, nextSteps }: SummaryCardProps) {
  return (
    <div className="mx-2 my-2 overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-b from-white to-slate-50/80 shadow-sm">
      <div className="px-4 py-3">
        <p className="text-sm leading-relaxed text-slate-700">{text}</p>
      </div>
      {findings.length > 0 ? (
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Findings</p>
          <ol className="space-y-1.5">
            {findings.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-700">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                <span>{f}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {nextSteps.length > 0 ? (
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Next Steps</p>
          <ol className="space-y-1.5">
            {nextSteps.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-700">
                <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-orange-500" />
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}
