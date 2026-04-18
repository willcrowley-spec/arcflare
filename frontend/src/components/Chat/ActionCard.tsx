import { useState } from 'react'
import type { ChatAction } from '@/types'
import { FilePlus, Link2, Loader2, Trash2, Wrench } from 'lucide-react'

function actionMeta(actionType: string): { label: string; Icon: typeof Wrench } {
  const t = actionType.toLowerCase()
  if (t.includes('create') && t.includes('process')) return { label: 'Create process', Icon: FilePlus }
  if (t.includes('resolve') && t.includes('gap')) return { label: 'Resolve gap', Icon: Link2 }
  if (t.includes('delete') && t.includes('process')) return { label: 'Delete process', Icon: Trash2 }
  return { label: actionType.replace(/_/g, ' '), Icon: Wrench }
}

function PayloadSummary({ action }: { action: ChatAction }) {
  const p = action.payload
  const t = action.action_type.toLowerCase()

  if (t.includes('create') && t.includes('process')) {
    return (
      <dl className="mt-2 space-y-1.5 text-sm text-slate-700">
        <div className="flex gap-2">
          <dt className="shrink-0 font-medium text-slate-500">Name</dt>
          <dd className="min-w-0 break-words">{String(p.name ?? '—')}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="shrink-0 font-medium text-slate-500">Description</dt>
          <dd className="min-w-0 break-words">{String(p.description ?? '—')}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="shrink-0 font-medium text-slate-500">Parent</dt>
          <dd className="min-w-0 break-words">{String(p.parent_id ?? p.parent ?? '—')}</dd>
        </div>
      </dl>
    )
  }

  if (t.includes('resolve') && t.includes('gap')) {
    return (
      <dl className="mt-2 space-y-1.5 text-sm text-slate-700">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Gap</dt>
          <dd className="mt-0.5 whitespace-pre-wrap break-words">{String(p.description ?? p.gap_description ?? '—')}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Resolution</dt>
          <dd className="mt-0.5 whitespace-pre-wrap break-words">{String(p.resolution_note ?? '—')}</dd>
        </div>
      </dl>
    )
  }

  if (t.includes('delete') && t.includes('process')) {
    return (
      <div className="mt-2 rounded-md border border-red-200 bg-red-50/60 px-3 py-2 text-sm text-red-900">
        <p className="font-medium">Cascade impact</p>
        <p className="mt-1 text-xs leading-relaxed text-red-800/90">
          Deleting this process may remove linked subprocesses, handoffs, and discovery artifacts depending on backend
          rules. Confirm only if you intend to remove this catalog entry.
        </p>
        {p.name != null ? (
          <p className="mt-2 text-xs font-semibold text-red-950">Target: {String(p.name)}</p>
        ) : null}
      </div>
    )
  }

  return (
    <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-white/80 p-2 text-xs text-slate-700 ring-1 ring-slate-200/80">
      {JSON.stringify(p, null, 2)}
    </pre>
  )
}

type ActionCardProps = {
  action: ChatAction
  onConfirm: (payloadOverride?: Record<string, unknown>) => Promise<void>
  onReject: () => Promise<void>
}

export function ActionCard({ action, onConfirm, onReject }: ActionCardProps) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [ui, setUi] = useState<'active' | 'success' | 'cancelled'>(action.status === 'rejected' ? 'cancelled' : 'active')
  const { label, Icon } = actionMeta(action.action_type)
  const t = action.action_type.toLowerCase()

  const [name, setName] = useState(String(action.payload.name ?? ''))
  const [description, setDescription] = useState(String(action.payload.description ?? ''))
  const [parent, setParent] = useState(String(action.payload.parent_id ?? action.payload.parent ?? ''))
  const [resolutionNote, setResolutionNote] = useState(String(action.payload.resolution_note ?? ''))

  if (ui === 'cancelled' || action.status === 'rejected') {
    return (
      <div className="mx-2 my-2 rounded-lg border border-slate-200 bg-slate-100/80 px-4 py-3 text-center text-xs font-medium text-slate-500">
        Cancelled
      </div>
    )
  }

  if (ui === 'success') {
    return (
      <div className="mx-2 my-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-center text-sm font-medium text-emerald-800">
        Confirmed
      </div>
    )
  }

  const handleConfirm = async () => {
    setBusy(true)
    try {
      if (editing) {
        let merged: Record<string, unknown> = { ...action.payload }
        if (t.includes('create') && t.includes('process')) {
          merged = { ...merged, name, description, parent_id: parent || null }
        } else if (t.includes('resolve') && t.includes('gap')) {
          merged = { ...merged, resolution_note: resolutionNote }
        }
        await onConfirm(merged)
      } else {
        await onConfirm()
      }
      setUi('success')
      setEditing(false)
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    setBusy(true)
    try {
      await onReject()
      setUi('cancelled')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-2 my-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 shadow-sm ring-1 ring-amber-100/80">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-800 ring-1 ring-amber-200/80">
          <Icon className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold capitalize text-slate-800">{label}</p>
          <p className="text-xs text-slate-500">Action requires your confirmation</p>
        </div>
      </div>

      {!editing ? <PayloadSummary action={action} /> : null}

      {editing ? (
        <div className="mt-3 space-y-3 rounded-md border border-amber-200/80 bg-white/90 p-3">
          {t.includes('create') && t.includes('process') ? (
            <>
              <label className="block text-xs font-medium text-slate-600">
                Name
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-800 shadow-sm focus:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400/30"
                />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Description
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-800 shadow-sm focus:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400/30"
                />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Parent ID
                <input
                  value={parent}
                  onChange={(e) => setParent(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-800 shadow-sm focus:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400/30"
                />
              </label>
            </>
          ) : null}
          {t.includes('resolve') && t.includes('gap') ? (
            <label className="block text-xs font-medium text-slate-600">
              Resolution note
              <textarea
                value={resolutionNote}
                onChange={(e) => setResolutionNote(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-800 shadow-sm focus:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400/30"
              />
            </label>
          ) : null}
          {!(t.includes('create') && t.includes('process')) && !(t.includes('resolve') && t.includes('gap')) ? (
            <p className="text-xs text-slate-500">No structured fields for this action type; confirm or cancel.</p>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleConfirm()}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60 sm:flex-none"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Confirm
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => setEditing((e) => !e)}
          className="inline-flex flex-1 items-center justify-center rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60 sm:flex-none"
        >
          {editing ? 'Preview' : 'Edit'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleReject()}
          className="inline-flex flex-1 items-center justify-center rounded-lg bg-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-60 sm:flex-none"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
