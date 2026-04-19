import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2, X } from 'lucide-react'
import clsx from 'clsx'
import { api } from '@/api/client'
import type { Document } from '@/types'

type DocumentDetailProps = {
  documentId: string | null
  initial: Document | null
  open: boolean
  onClose: () => void
}

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

function statusBadge(status: string) {
  const s = status.toLowerCase()
  if (s === 'indexed') {
    return 'bg-emerald-50 text-emerald-800 ring-emerald-200/80'
  }
  if (s === 'uploaded') {
    return 'bg-sky-50 text-sky-800 ring-sky-200/80'
  }
  if (s === 'processing' || s === 'uploading' || s === 'vectorizing' || s === 'analyzing') {
    return 'bg-amber-50 text-amber-900 ring-amber-200/80'
  }
  if (s === 'error' || s === 'failed') {
    return 'bg-red-50 text-red-800 ring-red-200/80'
  }
  return 'bg-slate-100 text-slate-700 ring-slate-200/80'
}

export function DocumentDetail({ documentId, initial, open, onClose }: DocumentDetailProps) {
  const queryClient = useQueryClient()
  const [tagInput, setTagInput] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const detailQuery = useQuery({
    queryKey: ['documents', 'detail', documentId],
    queryFn: () => api.documents.get(documentId!),
    enabled: open && !!documentId,
    refetchInterval: open && documentId ? 5000 : false,
  })

  const doc = detailQuery.data ?? initial

  const communitiesQuery = useQuery({
    queryKey: ['documents', 'communities', documentId],
    queryFn: () => api.documents.communities(documentId!),
    enabled: open && !!documentId,
  })

  const provenanceQuery = useQuery({
    queryKey: ['documents', 'provenance', documentId],
    queryFn: () => api.documents.provenance(documentId!),
    enabled: open && !!documentId,
  })

  const tagsMutation = useMutation({
    mutationFn: ({ id, tags }: { id: string; tags: string[] }) => api.documents.updateTags(id, tags),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      void queryClient.invalidateQueries({ queryKey: ['documents', 'detail', documentId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.documents.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      onClose()
    },
  })

  useEffect(() => {
    if (!open) {
      setConfirmDelete(false)
      setTagInput('')
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  const tags = doc?.tags ?? []

  const handleAddTag = () => {
    if (!doc) return
    const t = tagInput.trim()
    if (!t || tags.includes(t)) {
      setTagInput('')
      return
    }
    const next = [...tags, t]
    tagsMutation.mutate({ id: doc.id, tags: next })
    setTagInput('')
  }

  const handleRemoveTag = (tag: string) => {
    if (!doc) return
    tagsMutation.mutate({ id: doc.id, tags: tags.filter((x) => x !== tag) })
  }

  const provenanceIds = useMemo(() => provenanceQuery.data ?? [], [provenanceQuery.data])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close panel"
        className="absolute inset-0 bg-navy-900/40 backdrop-blur-[1px] transition-opacity"
        onClick={onClose}
      />
      <aside className="relative flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform duration-200 ease-out">
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Document</p>
            <h2 className="mt-1 break-words text-lg font-bold text-navy-900">
              {doc?.filename ?? (detailQuery.isLoading ? 'Loading…' : '—')}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-navy-900"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {detailQuery.isError ? (
            <p className="text-sm text-red-600">
              {detailQuery.error instanceof Error ? detailQuery.error.message : 'Could not load document.'}
            </p>
          ) : null}

          {doc ? (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={clsx(
                    'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1',
                    statusBadge(doc.status),
                  )}
                >
                  {doc.status}
                </span>
                {detailQuery.isFetching && !detailQuery.isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-slate-400" aria-hidden />
                ) : null}
              </div>

              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4 border-b border-slate-100 py-2">
                  <dt className="text-slate-500">File size</dt>
                  <dd className="font-medium text-navy-900">{formatBytes(doc.file_size_bytes)}</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-100 py-2">
                  <dt className="text-slate-500">Uploaded</dt>
                  <dd className="text-right font-medium text-navy-900">{formatDate(doc.created_at)}</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-100 py-2">
                  <dt className="text-slate-500">MIME type</dt>
                  <dd className="max-w-[60%] truncate font-medium text-navy-900">{doc.mime_type ?? '—'}</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-100 py-2">
                  <dt className="text-slate-500">Chunks</dt>
                  <dd className="font-medium text-navy-900">{doc.chunk_count}</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-100 py-2">
                  <dt className="text-slate-500">Concepts</dt>
                  <dd className="font-medium text-navy-900">{doc.concept_count}</dd>
                </div>
                {doc.error_message ? (
                  <div className="rounded-lg border border-red-200 bg-red-50/80 px-3 py-2">
                    <dt className="text-xs font-semibold uppercase text-red-800">Error</dt>
                    <dd className="mt-1 text-sm text-red-900">{doc.error_message}</dd>
                  </div>
                ) : null}
              </dl>

              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Tags</h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  {tags.map((t) => (
                    <button
                      key={t}
                      type="button"
                      disabled={tagsMutation.isPending}
                      onClick={() => handleRemoveTag(t)}
                      className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-800 ring-1 ring-slate-200/80 hover:bg-slate-200/80 disabled:opacity-50"
                      title="Click to remove"
                    >
                      {t}
                      <span className="text-slate-500">×</span>
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex gap-2">
                  <input
                    type="text"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleAddTag()
                      }
                    }}
                    placeholder="Add tag…"
                    className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-sm focus:border-navy-300 focus:outline-none focus:ring-2 focus:ring-navy-200"
                  />
                  <button
                    type="button"
                    onClick={handleAddTag}
                    disabled={!tagInput.trim() || tagsMutation.isPending}
                    className="rounded-lg bg-navy-800 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Add
                  </button>
                </div>
              </section>

              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Communities</h3>
                {communitiesQuery.isLoading ? (
                  <div className="mt-2 flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading…
                  </div>
                ) : communitiesQuery.isError ? (
                  <p className="mt-2 text-sm text-red-600">Could not load communities.</p>
                ) : (communitiesQuery.data?.length ?? 0) === 0 ? (
                  <p className="mt-2 text-sm text-slate-500">No communities linked yet.</p>
                ) : (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(communitiesQuery.data ?? []).map((c) => (
                      <span
                        key={c.id}
                        className="inline-flex max-w-full truncate rounded-full bg-violet-50 px-2.5 py-0.5 text-xs font-semibold text-violet-900 ring-1 ring-violet-200/80"
                      >
                        {c.label?.trim() || `Community ${c.id.slice(0, 8)}…`}
                      </span>
                    ))}
                  </div>
                )}
              </section>

              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Provenance</h3>
                {provenanceQuery.isLoading ? (
                  <div className="mt-2 flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading…
                  </div>
                ) : provenanceQuery.isError ? (
                  <p className="mt-2 text-sm text-red-600">Could not load provenance.</p>
                ) : provenanceIds.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-500">No linked processes yet.</p>
                ) : (
                  <ul className="mt-2 flex flex-col gap-2">
                    {provenanceIds.map((p) => (
                      <li key={p.id}>
                        <Link
                          to={`/processes/${p.process_id}/map`}
                          className="inline-flex rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 font-mono text-xs font-semibold text-navy-800 ring-1 ring-slate-200/80 hover:bg-white"
                        >
                          Process {p.process_id}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          ) : detailQuery.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading document…
            </div>
          ) : null}
        </div>

        <div className="border-t border-slate-100 px-5 py-4">
          {confirmDelete ? (
            <div className="space-y-3 rounded-lg border border-red-200 bg-red-50/60 p-3">
              <p className="text-sm font-medium text-red-900">Delete this document permanently?</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!doc || deleteMutation.isPending}
                  onClick={() => doc && deleteMutation.mutate(doc.id)}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
                >
                  {deleteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              disabled={!doc}
              onClick={() => setConfirmDelete(true)}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-700 shadow-sm hover:bg-red-50 disabled:opacity-40"
            >
              <Trash2 className="h-4 w-4" />
              Delete document
            </button>
          )}
        </div>
      </aside>
    </div>
  )
}
