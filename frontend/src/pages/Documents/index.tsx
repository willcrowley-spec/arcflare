import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { api } from '@/api/client'
import { SearchBar } from '@/components/SearchBar'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import type { Document } from '@/types'
import { UploadZone } from './UploadZone'
import { DocumentDetail } from './DocumentDetail'

const PAGE_SIZE = 12

function formatBytes(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = n
  let u = 0
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024
    u += 1
  }
  const digits = u === 0 ? 0 : u === 1 ? 1 : 2
  return `${v.toFixed(digits)} ${units[u]}`
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function statusBadgeClass(status: string) {
  const s = status.toLowerCase()
  if (s === 'indexed') return 'bg-emerald-50 text-emerald-800 ring-emerald-200/80'
  if (s === 'uploaded') return 'bg-sky-50 text-sky-800 ring-sky-200/80'
  if (s === 'processing' || s === 'uploading' || s === 'vectorizing' || s === 'analyzing') {
    return 'bg-amber-50 text-amber-900 ring-amber-200/80'
  }
  if (s === 'error' || s === 'failed') return 'bg-red-50 text-red-800 ring-red-200/80'
  return 'bg-slate-100 text-slate-700 ring-slate-200/80'
}

function StatusCell({ doc }: { doc: Document }) {
  const isProcessing = ['processing', 'uploading', 'uploaded'].includes(doc.status.toLowerCase())
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className={clsx(
          'inline-flex w-fit rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1',
          statusBadgeClass(doc.status),
        )}
      >
        {doc.status}
      </span>
      {isProcessing && doc.processing_phase && (
        <span className="flex items-center gap-1 text-[10px] text-amber-700">
          <Loader2 className="h-2.5 w-2.5 animate-spin" />
          {doc.processing_phase}
        </span>
      )}
    </div>
  )
}

function SummaryCell({ summary }: { summary: string | null }) {
  if (!summary) return <span className="text-xs text-slate-400">—</span>
  return (
    <span className="line-clamp-2 text-xs text-slate-600" title={summary}>
      {summary}
    </span>
  )
}

export default function DocumentsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedInitial, setSelectedInitial] = useState<Document | null>(null)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['documents', page, PAGE_SIZE],
    queryFn: () => api.documents.list({ page, page_size: PAGE_SIZE }),
    refetchInterval: 5000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1)

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    if (!qq) return items
    return items.filter((d) => d.filename.toLowerCase().includes(qq))
  }, [items, q])

  const openDetail = (doc: Document) => {
    setSelectedId(doc.id)
    setSelectedInitial(doc)
  }

  const closeDetail = () => {
    setSelectedId(null)
    setSelectedInitial(null)
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Documents</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Upload business documents, track vectorization status, and connect indexed knowledge to processes and
          communities.
        </p>
      </div>

      <UploadZone
        onUploadComplete={() => {
          void queryClient.invalidateQueries({ queryKey: ['documents'] })
        }}
      />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="max-w-xl flex-1">
          <SearchBar value={q} onChange={setQ} placeholder="Filter by filename…" />
        </div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {total === 0 ? 'No documents' : `Page ${page} · ${total} total`}
        </p>
      </div>

      {isLoading ? (
        <LoadingState message="Loading documents…" />
      ) : isError ? (
        <div className="space-y-4">
          <ErrorState message={error instanceof Error ? error.message : undefined} />
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
          >
            Retry
          </button>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="No documents yet"
          description="Upload PDFs, spreadsheets, or text files to build your searchable knowledge library."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="No matches"
          description="Try a different filename filter or clear the search box."
        />
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-3">Filename</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Size</th>
                    <th className="px-4 py-3">Uploaded</th>
                    <th className="px-4 py-3">Summary</th>
                    <th className="px-4 py-3">Chunks</th>
                    <th className="px-4 py-3">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((doc) => (
                    <tr
                      key={doc.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => openDetail(doc)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          openDetail(doc)
                        }
                      }}
                      className={clsx(
                        'cursor-pointer border-b border-slate-100 transition-colors last:border-b-0',
                        selectedId === doc.id ? 'bg-orange-50/40' : 'hover:bg-slate-50/80',
                      )}
                    >
                      <td className="max-w-[240px] px-4 py-3">
                        <span className="line-clamp-2 font-medium text-navy-900" title={doc.filename}>
                          {doc.filename}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <StatusCell doc={doc} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-700">{formatBytes(doc.file_size_bytes)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDate(doc.created_at)}</td>
                      <td className="max-w-[280px] px-4 py-3 align-top">
                        <SummaryCell summary={doc.summary ?? null} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-700">{doc.chunk_count}</td>
                      <td className="px-4 py-3">
                        <div className="flex max-w-[200px] flex-wrap gap-1">
                          {(doc.tags ?? []).slice(0, 5).map((t) => (
                            <span
                              key={t}
                              className="truncate rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200/80"
                            >
                              {t}
                            </span>
                          ))}
                          {(doc.tags?.length ?? 0) > 5 ? (
                            <span className="text-[11px] font-semibold text-slate-500">+{doc.tags!.length - 5}</span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {totalPages > 1 ? (
            <div className="flex items-center justify-center gap-4">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs font-medium text-slate-500">
                Page {page} / {totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      )}

      <DocumentDetail
        open={!!selectedId}
        documentId={selectedId}
        initial={selectedInitial}
        onClose={closeDetail}
      />
    </div>
  )
}
