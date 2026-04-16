import { type ReactNode } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-navy-700/30 bg-navy-950/30 px-8 py-16 text-center">
      {icon && <div className="text-navy-400">{icon}</div>}
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      {description && <p className="max-w-md text-sm text-navy-300">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24">
      <Loader2 className="h-8 w-8 animate-spin text-navy-400" />
      <p className="text-sm text-navy-300">{message}</p>
    </div>
  )
}

export function ErrorState({ message }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red-800/30 bg-red-950/20 px-8 py-16 text-center">
      <AlertCircle className="h-8 w-8 text-red-400" />
      <h3 className="text-lg font-semibold text-red-300">Something went wrong</h3>
      <p className="max-w-md text-sm text-red-300/70">{message || 'An unexpected error occurred. Please try again.'}</p>
    </div>
  )
}
