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
    <div className="flex w-full min-w-0 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-300 bg-white px-4 py-16 text-center shadow-sm sm:px-8">
      {icon && <div className="text-slate-400">{icon}</div>}
      <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
      {description && <p className="max-w-md text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24">
      <Loader2 className="h-8 w-8 animate-spin text-navy-500" />
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  )
}

export function ErrorState({ message }: { message?: string }) {
  return (
    <div className="flex w-full min-w-0 flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-16 text-center shadow-sm sm:px-8">
      <AlertCircle className="h-8 w-8 text-red-500" />
      <h3 className="text-lg font-semibold text-red-800">Something went wrong</h3>
      <p className="max-w-md text-sm text-red-600">{message || 'An unexpected error occurred. Please try again.'}</p>
    </div>
  )
}
