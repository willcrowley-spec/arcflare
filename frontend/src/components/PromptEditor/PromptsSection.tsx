import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { AlertCircle, ChevronDown, Info } from 'lucide-react'
import { usePromptBlocks, usePromptOperations } from '@/hooks/useApi'
import { PromptBlockCard } from './PromptBlockCard'

const GROUP_LABELS: Record<string, string> = {
  metadata: 'Metadata Pipeline',
  analysis: 'Analysis',
  discovery: 'Discovery Pipeline',
  synthesis: 'Synthesis',
  chat: 'Chat Assistant',
}

const GROUP_ORDER = ['metadata', 'analysis', 'discovery', 'synthesis', 'chat'] as const

function groupTitle(group: string): string {
  return GROUP_LABELS[group] ?? group
}

function systemContextText(operationId: string): string {
  if (operationId === 'chat') {
    return 'Automatically appended at runtime: available platform tools, organization settings JSON, conversation anchor context (when applicable), RAG search results (when applicable).'
  }
  if (operationId.startsWith('discovery_')) {
    return 'Automatically appended at runtime: organization context, platform metadata summary, document excerpts.'
  }
  return 'Automatically appended at runtime: operation-specific data context.'
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return 'Something went wrong.'
}

export function PromptsSection() {
  const operationsQuery = usePromptOperations()
  const [selectedOperationId, setSelectedOperationId] = useState<string | null>(null)
  const [systemContextOpen, setSystemContextOpen] = useState(false)

  const operations = operationsQuery.data?.operations ?? []

  useEffect(() => {
    if (!operations.length) return
    setSelectedOperationId((prev) => {
      if (prev && operations.some((o) => o.operation_id === prev)) return prev
      return operations[0].operation_id
    })
  }, [operations])

  const blocksQuery = usePromptBlocks(selectedOperationId)

  const groupsMap = useMemo(() => {
    const m = new Map<string, typeof operations>()
    for (const op of operations) {
      if (!m.has(op.group)) m.set(op.group, [])
      m.get(op.group)!.push(op)
    }
    return m
  }, [operations])

  const sortedGroupKeys = useMemo(() => {
    const keys = [...groupsMap.keys()]
    keys.sort((a, b) => {
      const ia = GROUP_ORDER.indexOf(a as (typeof GROUP_ORDER)[number])
      const ib = GROUP_ORDER.indexOf(b as (typeof GROUP_ORDER)[number])
      const ra = ia === -1 ? 999 : ia
      const rb = ib === -1 ? 999 : ib
      return ra - rb || a.localeCompare(b)
    })
    return keys
  }, [groupsMap])

  const opsLoading = operationsQuery.isLoading
  const blocksLoading = Boolean(selectedOperationId && blocksQuery.isLoading)

  const rightError = blocksQuery.isError
  const blocks = blocksQuery.data ?? []

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
      {operationsQuery.isError ? (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1">{errorMessage(operationsQuery.error)}</span>
          <button
            type="button"
            className="shrink-0 rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-100"
            onClick={() => void operationsQuery.refetch()}
          >
            Retry
          </button>
        </div>
      ) : null}

      <div className="flex gap-6">
        <aside className="w-[240px] shrink-0">
          {opsLoading ? (
            <div className="space-y-2">
              <div className="h-4 w-24 animate-pulse rounded bg-slate-100" />
              <div className="h-9 animate-pulse rounded-lg bg-slate-100" />
              <div className="h-9 animate-pulse rounded-lg bg-slate-100" />
              <div className="h-9 animate-pulse rounded-lg bg-slate-100" />
            </div>
          ) : (
            <nav className="space-y-4">
              {sortedGroupKeys.map((group) => (
                <div key={group}>
                  <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">{groupTitle(group)}</p>
                  <ul className="space-y-0.5">
                    {groupsMap.get(group)!.map((op) => {
                      const selected = op.operation_id === selectedOperationId
                      return (
                        <li key={op.operation_id}>
                          <button
                            type="button"
                            onClick={() => setSelectedOperationId(op.operation_id)}
                            className={clsx(
                              'w-full cursor-pointer rounded-lg px-3 py-2 text-left text-sm transition',
                              selected ? 'bg-navy-50 font-medium text-navy-800' : 'text-slate-700 hover:bg-slate-50',
                            )}
                          >
                            {op.label}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              ))}
            </nav>
          )}
        </aside>

        <div className="min-w-0 flex-1 space-y-4">
          {rightError ? (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1">{errorMessage(blocksQuery.error)}</span>
              <button
                type="button"
                className="shrink-0 rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-100"
                onClick={() => void blocksQuery.refetch()}
              >
                Retry
              </button>
            </div>
          ) : null}

          {opsLoading || blocksLoading ? (
            <div className="space-y-4">
              <div className="h-48 animate-pulse rounded-xl bg-slate-100" />
              <div className="h-48 animate-pulse rounded-xl bg-slate-100" />
              <div className="h-48 animate-pulse rounded-xl bg-slate-100" />
            </div>
          ) : !rightError && selectedOperationId ? (
            <>
              {blocks.length === 0 ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-4 py-6 text-center text-sm text-slate-500">
                  No prompt blocks configured for this operation.
                </div>
              ) : (
                <div className="space-y-4">
                  {blocks.map((block) => (
                    <PromptBlockCard key={block.block_type} block={block} operationId={selectedOperationId} />
                  ))}
                </div>
              )}

              <div className="border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setSystemContextOpen((o) => !o)}
                  className="flex w-full items-center gap-2 text-left text-sm font-medium text-slate-700"
                >
                  <ChevronDown
                    className={clsx('h-4 w-4 shrink-0 text-slate-500 transition-transform', systemContextOpen && 'rotate-180')}
                    aria-hidden
                  />
                  <span>System Context</span>
                  <span className="inline-flex items-center text-slate-400" title="Describes extra context merged with your prompts at runtime.">
                    <Info className="h-3.5 w-3.5" aria-hidden />
                  </span>
                </button>
                {systemContextOpen ? (
                  <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4 font-mono text-xs text-slate-500">
                    {systemContextText(selectedOperationId)}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
