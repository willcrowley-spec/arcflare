import { Search } from 'lucide-react'
import clsx from 'clsx'

type SearchBarProps = {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  className?: string
}

export function SearchBar({ value, onChange, placeholder = 'Search…', className }: SearchBarProps) {
  return (
    <div
      className={clsx(
        'flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm',
        className,
      )}
    >
      <Search className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full min-w-0 border-0 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-0"
      />
    </div>
  )
}
