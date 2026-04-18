import { useMemo } from 'react'
import clsx from 'clsx'
import { Database } from 'lucide-react'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { useUpdateClassification } from '@/hooks/useApi'
import type { MetadataObject } from '@/types'

const CLASSIFICATIONS = ['operational', 'configuration', 'deprecated'] as const
type ClassificationValue = (typeof CLASSIFICATIONS)[number]

const CLASS_SELECT_STYLE: Record<ClassificationValue, string> = {
  operational: 'bg-emerald-50 text-emerald-900 border-emerald-200',
  configuration: 'bg-sky-50 text-sky-900 border-sky-200',
  deprecated: 'bg-amber-50 text-amber-900 border-amber-200',
}

function normalizeClassification(raw: string | null | undefined): ClassificationValue {
  const v = (raw ?? '').toLowerCase().trim()
  if (v === 'empty') return 'deprecated'
  if (CLASSIFICATIONS.includes(v as ClassificationValue)) return v as ClassificationValue
  return 'deprecated'
}

function velocityPresentation(score: number | undefined, recordCount: number | undefined) {
  const s = score ?? 0
  const r = recordCount ?? 0
  if (r === 0) return { dot: 'bg-slate-300', label: 'none' as const }
  const pct = r > 0 ? s / r : 0
  if (pct > 0.5) return { dot: 'bg-emerald-500', label: 'hot' as const }
  if (s > 0) return { dot: 'bg-amber-500', label: 'warm' as const }
  return { dot: 'bg-slate-300', label: 'cold' as const }
}

export type DataObjectsTableProps = {
  rows: MetadataObject[]
  isLoading: boolean
}

export function DataObjectsTable({ rows, isLoading }: DataObjectsTableProps) {
  const updateClassification = useUpdateClassification()

  const columns: ColumnDef<MetadataObject>[] = useMemo(
    () => [
      {
        id: 'entity',
        header: 'Entity',
        className: 'min-w-[200px]',
        sortValue: (row) => `${row.label ?? ''} ${row.api_name}`.trim(),
        cell: (row) => (
          <div className="flex items-start gap-2">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-700">
              <Database className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-semibold text-navy-900">{row.label?.trim() || row.api_name}</p>
              <p className="truncate font-mono text-xs text-slate-500">{row.api_name}</p>
            </div>
          </div>
        ),
      },
      {
        id: 'type',
        header: 'Type',
        sortValue: (row) => row.object_type ?? '',
        cell: (row) => <span className="text-slate-700">{row.object_type?.trim() || '—'}</span>,
      },
      {
        id: 'classification',
        header: 'Classification',
        sortValue: (row) => normalizeClassification(row.classification),
        cell: (row) => {
          const pending =
            updateClassification.isPending && updateClassification.variables?.objectId === row.id
          const value = pending
            ? normalizeClassification(updateClassification.variables?.classification)
            : normalizeClassification(row.classification)
          const selectStyle = CLASS_SELECT_STYLE[value]

          return (
            <div
              className="inline-flex items-center"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <select
                aria-label={`Classification for ${row.api_name}`}
                className={clsx(
                  'cursor-pointer appearance-none rounded-full border px-3 py-1 text-xs font-semibold shadow-sm transition-colors',
                  selectStyle,
                  pending && 'opacity-50',
                )}
                value={value}
                disabled={pending}
                onChange={(e) => {
                  const next = e.target.value as ClassificationValue
                  updateClassification.mutate({ objectId: row.id, classification: next })
                }}
              >
                {CLASSIFICATIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          )
        },
      },
      {
        id: 'records',
        header: 'Records',
        sortValue: (row) => row.record_count ?? 0,
        cell: (row) => (
          <span className="tabular-nums text-slate-800">{(row.record_count ?? 0).toLocaleString()}</span>
        ),
      },
      {
        id: 'velocity',
        header: 'Velocity',
        sortValue: (row) => row.velocity_score ?? 0,
        cell: (row) => {
          const score = row.velocity_score ?? 0
          const { dot, label } = velocityPresentation(row.velocity_score, row.record_count)
          return (
            <div className="flex items-center gap-2">
              <span className={clsx('h-2.5 w-2.5 shrink-0 rounded-full', dot)} title={label} />
              <span className="tabular-nums text-slate-700">{score.toLocaleString()}</span>
            </div>
          )
        },
      },
      {
        id: 'automations',
        header: 'Automations',
        sortValue: (row) => row.automation_count ?? 0,
        cell: (row) => {
          const n = row.automation_count ?? 0
          return n === 0 ? <span className="text-slate-400">—</span> : <span className="tabular-nums">{n}</span>
        },
      },
    ],
    [updateClassification],
  )

  if (isLoading) {
    return (
      <div className="flex min-h-[240px] items-center justify-center rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
        <p className="text-sm text-slate-500">Loading data objects…</p>
      </div>
    )
  }

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      resourceName="objects"
      searchPlaceholder="Search entities…"
      pageSize={25}
      emptyLabel="No metadata objects for this connection."
      defaultSortCol="records"
      defaultSortDir="desc"
      getRowClassName={(r) => {
        const rc = r.record_count ?? 0
        const cls = normalizeClassification(r.classification)
        if (rc === 0 || cls === 'deprecated') return 'opacity-60'
        return undefined
      }}
    />
  )
}
