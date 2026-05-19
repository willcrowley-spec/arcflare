import { Loader2, Search } from 'lucide-react'
import type { ArcbrainSearchResult } from '@/types'
import { formatPercent } from '@/features/arcbrain/graph/model'

const TEMPLATE_QUESTIONS = [
  'What work can we replace without increasing customer risk?',
  'Which processes have high value but weak evidence?',
  'What depends on the selected node?',
  'Where are manual handoffs concentrated?',
  'What evidence supports the top replacement decision?',
]

interface ArcbrainAskRailProps {
  question: string
  setQuestion: (value: string) => void
  onAsk: (question?: string) => void
  isAsking: boolean
  error: unknown
  searchResult: ArcbrainSearchResult | null
  suggestedQuestions: string[]
  onSelectNode: (nodeId: string) => void
}

export function ArcbrainAskRail({
  question,
  setQuestion,
  onAsk,
  isAsking,
  error,
  searchResult,
  suggestedQuestions,
  onSelectNode,
}: ArcbrainAskRailProps) {
  const answer = searchResult?.answer ?? null
  const confidence = searchResult?.confidence ?? null
  const pathNodes = searchResult?.nodes ?? []
  const supportingClaims = searchResult?.supporting_claims ?? []

  return (
    <aside className="min-w-0 space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <div>
        <h2 className="text-base font-semibold text-navy-900">Ask the Brain</h2>
        <p className="mt-1 text-sm text-slate-600">Ask a business question and inspect the nodes Arcbrain used.</p>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold uppercase text-slate-500" htmlFor="arcbrain-question">
          Executive question
        </label>
        <textarea
          id="arcbrain-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
          className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-navy-200"
          placeholder="Ask about replacement, risk, evidence, or dependencies..."
        />
        <button
          type="button"
          disabled={isAsking || !question.trim()}
          onClick={() => onAsk()}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-navy-800 px-3 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isAsking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          {isAsking ? 'Investigating...' : 'Ask'}
        </button>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase text-slate-500">Templates</p>
        {(suggestedQuestions.length > 0 ? suggestedQuestions : TEMPLATE_QUESTIONS).slice(0, 5).map((template) => (
          <button
            key={template}
            type="button"
            onClick={() => onAsk(template)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-medium leading-relaxed text-slate-700 hover:border-navy-200 hover:bg-white"
          >
            <span className="block break-words">{template}</span>
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error instanceof Error ? error.message : 'Arcbrain search failed.'}
        </div>
      ) : null}

      {answer ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase text-slate-500">Answer</p>
            <span className="text-xs font-semibold text-slate-500">{formatPercent(confidence)}</span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{answer}</p>
          {pathNodes.length > 0 ? (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-semibold uppercase text-slate-500">Consulted nodes</p>
              <div className="flex flex-wrap gap-1.5">
                {pathNodes.slice(0, 8).map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelectNode(node.id)}
                    className="max-w-full truncate rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:border-orange-200 hover:text-orange-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-200"
                  >
                    {node.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {supportingClaims.length > 0 ? (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase text-slate-500">Evidence refs</p>
              <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-slate-600">
                {supportingClaims.slice(0, 5).map((item) => (typeof item === 'string' ? item : item.label ?? item.id ?? 'Evidence')).join(' / ')}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  )
}
