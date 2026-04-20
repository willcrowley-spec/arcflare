import { useMemo } from 'react'
import clsx from 'clsx'
import { Database, Eye, EyeOff } from 'lucide-react'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { useUpdateClassification } from '@/hooks/useApi'
import type { MetadataObject } from '@/types'

function isIncluded(raw: string | null | undefined): boolean {
  const v = (raw ?? '').toLowerCase().trim()
  return v !== 'excluded'
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
        id: 'included',
        header: 'Included',
        className: 'w-[80px]',
        sortValue: (row) => (isIncluded(row.classification) ? 1 : 0),
        cell: (row) => {
          const pending =
            updateClassification.isPending && updateClassification.variables?.objectId === row.id
          const included = pending
            ? isIncluded(updateClassification.variables?.classification)
            : isIncluded(row.classification)
          const Icon = included ? Eye : EyeOff

          return (
            <div
              className="inline-flex items-center"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                aria-label={`${included ? 'Exclude' : 'Include'} ${row.api_name}`}
                className={clsx(
                  'flex h-7 w-7 items-center justify-center rounded-md transition-all',
                  included
                    ? 'text-navy-700 hover:bg-navy-50 hover:text-navy-900'
                    : 'text-slate-300 hover:bg-slate-50 hover:text-slate-500',
                  pending && 'pointer-events-none opacity-40',
                )}
                disabled={pending}
                onClick={() => {
                  updateClassification.mutate({
                    objectId: row.id,
                    classification: included ? 'excluded' : 'included',
                  })
                }}
              >
                <Icon className="h-4 w-4" />
              </button>
            </div>
          )
        },
      },
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
        if (!isIncluded(r.classification)) return 'opacity-50'
        return undefined
      }}
    />
  )
}
