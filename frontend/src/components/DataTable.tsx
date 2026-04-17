import * as React from 'react'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import clsx from 'clsx'
import { SearchBar } from '@/components/SearchBar'

export type ColumnDef<T> = {
  id: string
  header: string
  className?: string
  cell: (row: T) => React.ReactNode
  sortValue?: (row: T) => string | number
}

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const

function getPageNumbers(current: number, total: number): (number | 'ellipsis')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i)
  const pages: (number | 'ellipsis')[] = [0]
  const start = Math.max(1, current - 1)
  const end = Math.min(total - 2, current + 1)
  if (start > 1) pages.push('ellipsis')
  for (let i = start; i <= end; i++) pages.push(i)
  if (end < total - 2) pages.push('ellipsis')
  pages.push(total - 1)
  return [...new Set(pages)]
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
  const [userPageSize, setUserPageSize] = React.useState(pageSize)

  const pageSizeChoices = React.useMemo(() => {
    const set = new Set<number>([...PAGE_SIZE_OPTIONS, pageSize])
    return Array.from(set).sort((a, b) => a - b)
  }, [pageSize])

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
  const pageCount = Math.max(1, Math.ceil(total / userPageSize))
  const safePage = Math.min(page, pageCount - 1)
  const start = safePage * userPageSize
  const slice = sorted.slice(start, start + userPageSize)
  const pageNumbers = getPageNumbers(safePage, pageCount)
  const isFirstPage = safePage <= 0
  const isLastPage = safePage >= pageCount - 1

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
          Viewing {total === 0 ? 0 : start + 1}-{Math.min(start + userPageSize, total)} of {total} {resourceName}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/80">
              {columns.map((c) => {
                const isSortable = !!c.sortValue
                const isSorted = sortCol === c.id
                return (
                  <th
                    key={c.id}
                    className={clsx(
                      'px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500',
                      isSortable && 'cursor-pointer select-none hover:text-slate-800 focus-visible:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-navy-200',
                      c.className,
                    )}
                    onClick={() => isSortable && toggleSort(c.id)}
                    onKeyDown={(e) => {
                      if (isSortable && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault()
                        toggleSort(c.id)
                      }
                    }}
                    tabIndex={isSortable ? 0 : undefined}
                    role={isSortable ? 'button' : undefined}
                    aria-sort={isSorted ? (sortDir === 'asc' ? 'ascending' : 'descending') : isSortable ? 'none' : undefined}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.header}
                      {isSorted ? (
                        <span className="text-[10px] text-navy-600">{sortDir === 'asc' ? '▲' : '▼'}</span>
                      ) : null}
                    </span>
                  </th>
                )
              })}
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
      <div className="flex flex-col gap-3 border-t border-slate-100 px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <p className="text-sm text-slate-600">
            Showing{' '}
            <span className="font-medium text-slate-800">
              {total === 0 ? 0 : start + 1}-{Math.min(start + userPageSize, total)}
            </span>{' '}
            of <span className="font-medium text-slate-800">{total}</span> {resourceName}
          </p>
          <label className="inline-flex items-center gap-2 text-sm text-slate-600">
            <span className="whitespace-nowrap">Rows per page</span>
            <select
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-800"
              value={userPageSize}
              onChange={(e) => {
                setUserPageSize(Number(e.target.value))
                setPage(0)
              }}
            >
              {pageSizeChoices.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            aria-label="First page"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => setPage(0)}
            disabled={isFirstPage}
          >
            <ChevronsLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label="Previous page"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={isFirstPage}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          {pageNumbers.map((item, idx) =>
            item === 'ellipsis' ? (
              <span key={`e-${idx}`} className="px-1 text-slate-400" aria-hidden>
                ...
              </span>
            ) : (
              <button
                key={item}
                type="button"
                className={clsx(
                  'h-10 w-10 rounded-lg text-sm font-medium',
                  item === safePage
                    ? 'bg-navy-800 text-white'
                    : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                )}
                onClick={() => setPage(item)}
                aria-label={`Page ${item + 1}`}
                aria-current={item === safePage ? 'page' : undefined}
              >
                {item + 1}
              </button>
            ),
          )}
          <button
            type="button"
            aria-label="Next page"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={isLastPage}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label="Last page"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => setPage(pageCount - 1)}
            disabled={isLastPage}
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
