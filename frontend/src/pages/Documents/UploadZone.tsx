import { useCallback, useId, useState } from 'react'
import { Upload } from 'lucide-react'
import clsx from 'clsx'
import { api } from '@/api/client'

type FileUploadState = {
  key: string
  file: File
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

type UploadZoneProps = {
  onUploadComplete?: () => void
  disabled?: boolean
}

function newUploadKey() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function UploadZone({ onUploadComplete, disabled }: UploadZoneProps) {
  const inputId = useId()
  const [dragOver, setDragOver] = useState(false)
  const [items, setItems] = useState<FileUploadState[]>([])

  const uploadAll = useCallback(
    async (files: File[]) => {
      if (!files.length || disabled) return

      const nextItems: FileUploadState[] = files.map((file) => ({
        key: newUploadKey(),
        file,
        status: 'pending' as const,
      }))
      setItems((prev) => [...nextItems, ...prev])

      await Promise.all(
        nextItems.map(async (entry) => {
          const { key } = entry
          setItems((prev) =>
            prev.map((x) => (x.key === key ? { ...x, status: 'uploading' as const } : x)),
          )
          try {
            await api.documents.upload(entry.file)
            setItems((prev) => prev.map((x) => (x.key === key ? { ...x, status: 'done' as const } : x)))
          } catch (e) {
            const message = e instanceof Error ? e.message : 'Upload failed'
            setItems((prev) =>
              prev.map((x) =>
                x.key === key ? { ...x, status: 'error' as const, error: message } : x,
              ),
            )
          }
        }),
      )

      onUploadComplete?.()
    },
    [disabled, onUploadComplete],
  )

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files
    if (!list?.length) return
    void uploadAll(Array.from(list))
    e.target.value = ''
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const list = e.dataTransfer.files
    if (!list?.length) return
    void uploadAll(Array.from(list))
  }

  return (
    <div className="space-y-3">
      <label
        htmlFor={inputId}
        onDragEnter={(e) => {
          e.preventDefault()
          if (!disabled) setDragOver(true)
        }}
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={clsx(
          'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors',
          disabled
            ? 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-400'
            : dragOver
              ? 'border-orange-400 bg-orange-50/50 ring-2 ring-orange-200/60'
              : 'border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50/80',
        )}
      >
        <input
          id={inputId}
          type="file"
          multiple
          className="sr-only"
          disabled={disabled}
          onChange={onInputChange}
        />
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-navy-800/5 text-navy-800 ring-1 ring-navy-900/10">
          <Upload className="h-6 w-6" aria-hidden />
        </span>
        <p className="mt-4 text-sm font-semibold text-navy-900">Drop files here or click to browse</p>
        <p className="mt-1 max-w-md text-xs text-slate-500">
          Files upload immediately. Large documents may take a few minutes to index in the background.
        </p>
      </label>

      {items.length > 0 ? (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white text-sm shadow-sm ring-1 ring-slate-900/5">
          {items.map((row) => (
            <li key={row.key} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate font-medium text-navy-900">{row.file.name}</p>
                {row.status === 'error' && row.error ? (
                  <p className="mt-0.5 text-xs text-red-600">{row.error}</p>
                ) : null}
              </div>
              <span
                className={clsx(
                  'shrink-0 text-xs font-semibold uppercase tracking-wide',
                  row.status === 'done' && 'text-emerald-700',
                  row.status === 'uploading' && 'text-amber-700',
                  row.status === 'pending' && 'text-slate-500',
                  row.status === 'error' && 'text-red-700',
                )}
              >
                {row.status === 'pending' && 'Queued'}
                {row.status === 'uploading' && 'Uploading…'}
                {row.status === 'done' && 'Done'}
                {row.status === 'error' && 'Error'}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
