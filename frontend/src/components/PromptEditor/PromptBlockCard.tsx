import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { Check, Loader2, Lock, RotateCcw } from 'lucide-react'
import { useRestorePromptBlock, useUpdatePromptBlock } from '@/hooks/useApi'
import type { PromptBlock } from '@/types'

interface Props {
  block: PromptBlock
  operationId: string
}

function parseMissingVarsFromError(err: unknown): string[] | null {
  if (typeof err !== 'object' || err === null || !('status' in err) || !('body' in err)) return null
  const status = (err as { status: number }).status
  const body = (err as { body: string }).body
  if (status !== 422) return null
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    const d = parsed.detail
    if (
      d &&
      typeof d === 'object' &&
      Array.isArray((d as { missing_required_variables?: unknown }).missing_required_variables)
    ) {
      return (d as { missing_required_variables: string[] }).missing_required_variables
    }
  } catch {
    /* ignore */
  }
  return null
}

export function PromptBlockCard({ block, operationId }: Props) {
  const [editedContent, setEditedContent] = useState(block.content)
  const [confirmRestore, setConfirmRestore] = useState(false)
  const [savePhase, setSavePhase] = useState<'idle' | 'saving' | 'success'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const updateMutation = useUpdatePromptBlock()
  const restoreMutation = useRestorePromptBlock()

  useEffect(() => {
    setEditedContent(block.content)
  }, [block.content, block.version, block.block_type])

  useEffect(() => {
    if (!block.is_customized) setConfirmRestore(false)
  }, [block.is_customized])

  const dirty = editedContent !== block.content

  const onSave = async () => {
    setSaveError(null)
    setSavePhase('saving')
    try {
      await updateMutation.mutateAsync({
        operationId,
        blockType: block.block_type,
        content: editedContent,
      })
      setSavePhase('success')
      window.setTimeout(() => setSavePhase('idle'), 2000)
    } catch (e) {
      setSavePhase('idle')
      const missing = parseMissingVarsFromError(e)
      if (missing?.length) {
        setSaveError(`Missing required variables: ${missing.map((v) => `\`${v}\``).join(', ')}`)
      } else {
        setSaveError('Could not save. Try again.')
      }
    }
  }

  const onConfirmRestore = async () => {
    setSaveError(null)
    try {
      await restoreMutation.mutateAsync({ operationId, blockType: block.block_type })
      setConfirmRestore(false)
    } catch {
      setSaveError('Could not restore defaults.')
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{block.label}</h3>
        {block.is_locked ? <Lock className="h-4 w-4 shrink-0 text-slate-400" aria-hidden /> : null}
        {block.is_customized ? (
          <span className="text-xs rounded-full border border-orange-200 bg-orange-50 px-2 py-0.5 text-orange-700">
            Customized
          </span>
        ) : null}
      </div>

      <textarea
        value={editedContent}
        disabled={block.is_locked}
        onChange={(e) => {
          setEditedContent(e.target.value)
          setSaveError(null)
        }}
        className={clsx(
          'min-h-[120px] w-full rounded-lg border border-slate-200 p-3 font-mono text-sm',
          'focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none',
          block.is_locked && 'cursor-not-allowed bg-slate-50 text-slate-400',
        )}
        spellCheck={false}
      />

      {saveError ? <p className="mt-1 text-xs text-red-600">{saveError}</p> : null}

      {block.available_vars.length > 0 ? (
        <p className="mt-1 text-xs text-slate-400">
          Available variables:{' '}
          {block.available_vars.map((v) => (
            <code key={v} className="mx-0.5 rounded bg-slate-100 px-1 font-mono">
              {v}
            </code>
          ))}
        </p>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="min-h-[28px]">
          {block.is_customized ? (
            confirmRestore ? (
              <span className="text-xs text-slate-600">
                Restore?{' '}
                <button
                  type="button"
                  className="font-semibold text-red-600 hover:underline"
                  onClick={() => void onConfirmRestore()}
                  disabled={restoreMutation.isPending}
                >
                  Yes
                </button>
                {' / '}
                <button type="button" className="text-slate-500 hover:text-slate-700" onClick={() => setConfirmRestore(false)}>
                  No
                </button>
              </span>
            ) : (
              <button
                type="button"
                title="Restore defaults"
                className="rounded p-1 text-slate-400 transition hover:text-orange-600"
                onClick={() => setConfirmRestore(true)}
                disabled={restoreMutation.isPending}
              >
                <RotateCcw className="h-4 w-4" aria-hidden />
              </button>
            )
          ) : null}
        </div>

        <button
          type="button"
          onClick={() => void onSave()}
          disabled={!dirty || block.is_locked || savePhase === 'saving' || savePhase === 'success'}
          className={clsx(
            'inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-1.5 text-sm text-white',
            savePhase === 'success'
              ? 'cursor-default'
              : (!dirty || block.is_locked || savePhase === 'saving') && 'cursor-not-allowed opacity-50',
          )}
        >
          {savePhase === 'saving' ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Save
            </>
          ) : savePhase === 'success' ? (
            <Check className="h-4 w-4 text-green-500" aria-hidden />
          ) : (
            'Save'
          )}
        </button>
      </div>
    </div>
  )
}
