import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileText, Loader2, Sparkles, Trash2, X } from 'lucide-react'
import clsx from 'clsx'
import { api } from '@/api/client'
import type { Document, DocumentChunk, DocumentConcept } from '@/types'

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
  if (s === 'indexed') return 'bg-emerald-50 text-emerald-800 ring-emerald-200/80'
  if (s === 'uploaded') return 'bg-sky-50 text-sky-800 ring-sky-200/80'
  if (['processing', 'uploading', 'vectorizing', 'analyzing'].includes(s)) {
    return 'bg-amber-50 text-amber-900 ring-amber-200/80'
  }
  if (s === 'error' || s === 'failed') return 'bg-red-50 text-red-800 ring-red-200/80'
  return 'bg-slate-100 text-slate-700 ring-slate-200/80'
}

const PHASE_LABELS: Record<string, string> = {
  downloading: 'Downloading file…',
  parsing: 'Parsing document…',
  embedding: 'Generating embeddings…',
  'extracting concepts': 'Extracting concepts…',
  summarizing: 'Generating summary…',
}

function ProcessingProgress({ phase }: { phase: string | null }) {
  const steps = ['downloading', 'parsing', 'embedding', 'extracting concepts', 'summarizing']
  const currentIdx = phase ? steps.indexOf(phase) : -1

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-amber-700" />
        <span className="text-sm font-semibold text-amber-900">
          {phase ? PHASE_LABELS[phase] ?? `${phase}…` : 'Processing…'}
        </span>
      </div>
      <div className="flex gap-1">
        {steps.map((step, i) => (
          <div
            key={step}
            className={clsx(
              'h-1.5 flex-1 rounded-full transition-colors',
              i < currentIdx
                ? 'bg-amber-500'
                : i === currentIdx
                  ? 'animate-pulse bg-amber-400'
                  : 'bg-amber-200',
            )}
          />
        ))}
      </div>
    </div>
  )
}

function ChunkCard({ chunk }: { chunk: DocumentChunk }) {
  const [expanded, setExpanded] = useState(false)
  const hasContext = !!chunk.contextualized_content && chunk.contextualized_content !== chunk.content

  return (
    <div className="rounded-lg border border-slate-200 bg-white text-sm">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50/80"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
        )}
        <span className="flex-1 truncate text-navy-900">
          {chunk.section_title || `Chunk ${chunk.chunk_index + 1}`}
        </span>
        {chunk.page_number != null && (
          <span className="shrink-0 text-[11px] text-slate-400">p.{chunk.page_number}</span>
        )}
      </button>
      {expanded && (
        <div className="border-t border-slate-100 px-3 py-2.5">
          {hasContext && (
            <div className="mb-2 rounded border border-violet-100 bg-violet-50/50 px-2.5 py-1.5">
              <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-violet-500">
                AI Context
              </p>
              <p className="text-xs leading-relaxed text-violet-900">
                {chunk.contextualized_content}
              </p>
            </div>
          )}
          <p className="whitespace-pre-wrap leading-relaxed text-slate-700">
            {chunk.content ?? '(empty)'}
          </p>
        </div>
      )}
    </div>
  )
}

export function DocumentDetail({ documentId, initial, open, onClose }: DocumentDetailProps) {
  const queryClient = useQueryClient()
  const [tagInput, setTagInput] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const isProcessing = (s?: string) =>
    s != null && ['processing', 'uploading', 'uploaded'].includes(s.toLowerCase())

  const detailQuery = useQuery({
    queryKey: ['documents', 'detail', documentId],
    queryFn: () => api.documents.get(documentId!),
    enabled: open && !!documentId,
    refetchInterval: open && documentId ? 3000 : false,
  })

  const doc = detailQuery.data ?? initial

  const chunksQuery = useQuery({
    queryKey: ['documents', 'chunks', documentId],
    queryFn: () => api.documents.chunks(documentId!),
    enabled: open && !!documentId && !isProcessing(doc?.status),
    staleTime: 60_000,
  })

  const conceptsQuery = useQuery({
    queryKey: ['documents', 'concepts', documentId],
    queryFn: () => api.documents.concepts(documentId!),
    enabled: open && !!documentId && !isProcessing(doc?.status),
    staleTime: 60_000,
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
  const concepts = conceptsQuery.data ?? []
  const chunks = chunksQuery.data ?? []

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close panel"
        className="absolute inset-0 bg-navy-900/40 backdrop-blur-[1px] transition-opacity"
        onClick={onClose}
      />
      <aside className="relative flex h-full w-full max-w-lg flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform duration-200 ease-out">
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

              {isProcessing(doc.status) && <ProcessingProgress phase={doc.processing_phase ?? null} />}

              {doc.summary && (
                <section>
                  <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <Sparkles className="h-3.5 w-3.5 text-violet-500" />
                    Summary
                  </h3>
                  <p className="mt-2 rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2.5 text-sm leading-relaxed text-navy-900">
                    {doc.summary}
                  </p>
                </section>
              )}

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

              {concepts.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Key Concepts
                  </h3>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {concepts.map((c) => (
                      <span
                        key={c.id}
                        title={`${c.display_name ?? c.name} (${c.frequency})`}
                        className="rounded-full bg-violet-50 px-2.5 py-0.5 text-xs font-medium text-violet-900 ring-1 ring-violet-200/80"
                      >
                        {c.display_name ?? c.name}
                      </span>
                    ))}
                  </div>
                </section>
              )}

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

              {chunks.length > 0 && (
                <section>
                  <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <FileText className="h-3.5 w-3.5" />
                    Chunks ({chunks.length})
                  </h3>
                  <div className="mt-2 space-y-2">
                    {chunks.map((chunk) => (
                      <ChunkCard key={chunk.id} chunk={chunk} />
                    ))}
                  </div>
                </section>
              )}

              {provenanceIds.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Provenance
                  </h3>
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
                </section>
              )}
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
