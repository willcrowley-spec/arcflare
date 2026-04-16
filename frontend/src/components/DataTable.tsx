import * as React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { SearchBar } from '@/components/SearchBar'

export type ColumnDef<T> = {
  id: string
  header: string
  className?: string
  cell: (row: T) => React.ReactNode
  sortValue?: (row: T) => string | number
}

type DataTableProps<T> = {
  columns: ColumnDef<T>[]
  rows: T[]
  rowKey: (row: T) => string
  searchPlaceholder?: string
  pageSize?: number
  onRowClick?: (row: T) => void
  emptyLabel?: string
  resourceName?: string
  showSearch?: boolean
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  searchPlaceholder = 'Search table…',
  pageSize = 8,
  onRowClick,
  emptyLabel = 'No rows to display',
  resourceName = 'items',
  showSearch = true,
}: DataTableProps<T>) {
  const [query, setQuery] = React.useState('')
  const [sortCol, setSortCol] = React.useState<string | null>(null)
  const [sortDir, setSortDir] = React.useState<'asc' | 'desc'>('asc')
  const [page, setPage] = React.useState(0)

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) =>
      columns.some((c) => {
        const v = c.sortValue?.(r)
        if (v === undefined) return false
        return String(v).toLowerCase().includes(q)
      }),
    )
  }, [columns, query, rows])

  const sorted = React.useMemo(() => {
    if (!sortCol) return filtered
    const col = columns.find((c) => c.id === sortCol)
    if (!col?.sortValue) return filtered
    const copy = [...filtered]
    copy.sort((a, b) => {
      const av = col.sortValue!(a)
      const bv = col.sortValue!(b)
      const cmp =
        typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv), undefined, { sensitivity: 'base' })
      return sortDir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [columns, filtered, sortCol, sortDir])

  const total = sorted.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const start = safePage * pageSize
  const slice = sorted.slice(start, start + pageSize)

  React.useEffect(() => {
    setPage(0)
  }, [query, sortCol, sortDir, rows.length])

  function toggleSort(id: string) {
    const col = columns.find((c) => c.id === id)
    if (!col?.sortValue) return
    if (sortCol !== id) {
      setSortCol(id)
      setSortDir('asc')
      return
    }
    setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
      <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
        {showSearch ? (
          <SearchBar value={query} onChange={setQuery} placeholder={searchPlaceholder} className="sm:max-w-sm" />
        ) : (
          <div />
        )}
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Viewing {total === 0 ? 0 : start + 1}-{Math.min(start + pageSize, total)} of {total} {resourceName}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/80">
              {columns.map((c) => (
                <th
                  key={c.id}
                  className={clsx(
                    'px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500',
                    c.sortValue && 'cursor-pointer select-none hover:text-slate-800',
                    c.className,
                  )}
                  onClick={() => c.sortValue && toggleSort(c.id)}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.header}
                    {sortCol === c.id ? (
                      <span className="text-[10px] text-navy-600">{sortDir === 'asc' ? '▲' : '▼'}</span>
                    ) : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.length === 0 ? (
              <tr>
                <td className="px-4 py-10 text-center text-sm text-slate-500" colSpan={columns.length}>
                  {emptyLabel}
                </td>
              </tr>
            ) : (
              slice.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={() => onRowClick?.(row)}
                  className={clsx(
                    'border-b border-slate-100 last:border-0',
                    onRowClick && 'cursor-pointer hover:bg-slate-50/80',
                  )}
                >
                  {columns.map((c) => (
                    <td key={c.id} className={clsx('px-4 py-3 align-middle text-slate-800', c.className)}>
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={safePage <= 0}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-xs font-medium text-slate-500">
          Page {safePage + 1} / {pageCount}
        </span>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
          disabled={safePage >= pageCount - 1}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
