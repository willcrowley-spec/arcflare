import { Loader2 } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'

const PHASE_LABELS: Record<string, string> = {
  building_context: 'Searching knowledge base…',
  thinking: '{name} is analyzing…',
}

export function ThinkingIndicator() {
  const phase = useChatStore((s) => s.thinkingPhase)
  const name = useChatStore((s) => s.agentName)

  if (!phase) return null

  const label = (PHASE_LABELS[phase] ?? `${name} is thinking…`).replace('{name}', name)

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-orange-500" />
      <span className="text-xs font-medium text-slate-500">{label}</span>
    </div>
  )
}
