import { NavLink, Outlet } from 'react-router-dom'
import { SignedIn, SignedOut, SignInButton, UserButton } from '@clerk/clerk-react'
import { Bot, Bell, Settings, User } from 'lucide-react'
import clsx from 'clsx'
import { clerkEnabled } from '@/main'

const nav = [
  { to: '/analysis', label: 'Analysis' },
  { to: '/organization', label: 'Organization' },
  { to: '/processes', label: 'Processes' },
  { to: '/recommendations', label: 'Recommendations' },
  { to: '/agents', label: 'Agents' },
]

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          'relative pb-3 text-sm font-medium transition-colors',
          isActive ? 'text-white' : 'text-slate-300 hover:text-white',
        )
      }
    >
      {({ isActive }) => (
        <>
          {label}
          <span
            className={clsx(
              'absolute inset-x-0 -bottom-px h-0.5 rounded-full transition-opacity',
              isActive ? 'bg-orange-400 opacity-100' : 'bg-transparent opacity-0',
            )}
          />
        </>
      )}
    </NavLink>
  )
}

export function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <header className="border-b border-white/10 bg-navy-800 text-white shadow-md">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-6 px-6 py-4">
          <div className="flex items-center gap-10">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/10">
                <Bot className="h-5 w-5 text-orange-300" strokeWidth={1.75} />
              </span>
              <div className="leading-tight">
                <p className="text-sm font-semibold tracking-tight">Arcflare</p>
                <p className="text-[11px] text-slate-300">Enterprise Intelligence</p>
              </div>
            </div>
            <nav className="hidden items-center gap-8 md:flex">
              {nav.map((item) => (
                <NavItem key={item.to} {...item} />
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg p-2 text-slate-200 hover:bg-white/10 hover:text-white"
              aria-label="Notifications"
            >
              <Bell className="h-5 w-5" />
            </button>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-200 hover:bg-white/10 hover:text-white"
              aria-label="Settings"
            >
              <Settings className="h-5 w-5" />
            </button>
            {clerkEnabled ? (
              <>
                <SignedIn>
                  <UserButton
                    appearance={{
                      elements: {
                        userButtonAvatarBox: 'h-9 w-9 ring-2 ring-white/20',
                      },
                    }}
                  />
                </SignedIn>
                <SignedOut>
                  <SignInButton mode="modal">
                    <button
                      type="button"
                      className="rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium text-white ring-1 ring-white/15 hover:bg-white/15"
                    >
                      Sign in
                    </button>
                  </SignInButton>
                </SignedOut>
              </>
            ) : (
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 ring-2 ring-white/20">
                <User className="h-5 w-5 text-slate-200" />
              </span>
            )}
          </div>
        </div>
        <div className="border-t border-white/10 px-6 py-2 md:hidden">
          <nav className="flex flex-wrap gap-x-4 gap-y-2">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx('text-sm', isActive ? 'text-orange-300' : 'text-slate-300')
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-3 px-6 py-6 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
          <p>© 2024 Arcflare AI. All rights reserved.</p>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <a className="hover:text-navy-800" href="#">
              System Status
            </a>
            <a className="hover:text-navy-800" href="#">
              API Docs
            </a>
            <a className="hover:text-navy-800" href="#">
              Support
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
