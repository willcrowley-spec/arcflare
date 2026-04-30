import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  OrganizationList,
  OrganizationSwitcher,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
  useAuth,
} from '@clerk/clerk-react'
import { Bot, User, Zap, Shield, BarChart3, ArrowRight } from 'lucide-react'
import clsx from 'clsx'
import { clerkEnabled } from '@/main'
import { ChatLauncher } from '@/components/Chat/ChatLauncher'
import { ChatPanel } from '@/components/Chat/ChatPanel'

function useClerkAuthSafe() {
  if (!clerkEnabled) return { isSignedIn: false, isLoaded: true, orgId: null }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useAuth()
}

const nav = [
  { to: '/analysis', label: 'Analysis' },
  { to: '/organization', label: 'Organization' },
  { to: '/processes', label: 'Processes' },
  { to: '/documents', label: 'Documents' },
  { to: '/recommendations', label: 'Recommendations' },
  { to: '/agents', label: 'Agents' },
]

const headerOrganizationSwitcherAppearance = {
  elements: {
    organizationSwitcherTrigger:
      'h-9 max-w-[190px] rounded-lg bg-white/10 px-2.5 text-white ring-1 ring-white/15 transition-colors hover:bg-white/15 focus-visible:ring-2 focus-visible:ring-orange-300',
    organizationSwitcherTriggerIcon: 'h-4 w-4 text-slate-200',
    organizationPreview: 'min-w-0 gap-2',
    organizationPreviewAvatarContainer: 'shrink-0',
    organizationPreviewAvatarBox:
      'h-6 w-6 rounded-md bg-orange-500 text-white ring-1 ring-white/20',
    organizationPreviewTextContainer: 'min-w-0',
    organizationPreviewMainIdentifier: 'min-w-0 max-w-[126px] truncate text-sm font-semibold text-white',
    organizationPreviewMainIdentifierText: 'truncate text-white',
    organizationPreviewSecondaryIdentifier: 'text-xs text-slate-300',
  },
}

const salesforceConnectionErrorMessages: Record<string, string> = {
  salesforce_authorization_blocked:
    'Salesforce blocked this OAuth flow because the External Client App cannot authorize a different Salesforce org. Install or package the app for that org, or use org-specific OAuth credentials.',
  salesforce_access_denied: 'Salesforce access was denied before Arcflare received an authorization code.',
  missing_authorization_code: 'Salesforce did not return an authorization code.',
  invalid_state: 'The Salesforce authorization session expired. Start the connection again.',
  token_exchange_failed: 'Arcflare could not exchange the Salesforce authorization code for tokens.',
  salesforce_already_connected: 'This Arcflare organization already has a Salesforce connection.',
  salesforce_org_mismatch: 'That reauthorization belongs to a different Salesforce org.',
}

function formatSalesforceConnectionError(error: string) {
  return salesforceConnectionErrorMessages[error] ?? error.replace(/_/g, ' ')
}

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

function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-navy-900">
      <header className="border-b border-white/10 bg-navy-900">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-5">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/10">
              <Bot className="h-5 w-5 text-orange-300" strokeWidth={1.75} />
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-tight text-white">Arcflare</p>
              <p className="text-[11px] text-slate-400">Enterprise Intelligence</p>
            </div>
          </div>
          <SignInButton mode="modal">
            <button
              type="button"
              className="rounded-lg bg-orange-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-orange-500/25 transition-all hover:bg-orange-400 hover:shadow-orange-400/30"
            >
              Sign in
            </button>
          </SignInButton>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 py-20">
        <div className="max-w-2xl text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-orange-500/30 bg-orange-500/10 px-4 py-1.5 text-xs font-medium text-orange-300">
            <Zap className="h-3.5 w-3.5" />
            Enterprise Platform Intelligence
          </div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-white sm:text-5xl">
            Connect. Analyze.{' '}
            <span className="text-orange-400">Transform.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-lg text-lg text-slate-400">
            Ingest metadata from Salesforce and business documents, discover automation opportunities, and
            quantify ROI with AI-powered recommendations.
          </p>
          <div className="mt-10">
            <SignInButton mode="modal">
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-lg bg-orange-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-orange-500/25 transition-all hover:bg-orange-400 hover:shadow-orange-400/30"
              >
                Get started
                <ArrowRight className="h-4 w-4" />
              </button>
            </SignInButton>
          </div>
        </div>

        <div className="mt-20 grid max-w-3xl gap-6 sm:grid-cols-3">
          {[
            {
              icon: BarChart3,
              title: 'Platform Analysis',
              desc: 'Connect Salesforce orgs and inspect metadata, record velocity, and automation coverage.',
            },
            {
              icon: Shield,
              title: 'Process Discovery',
              desc: 'Auto-generate business process maps from metadata and uploaded documents.',
            },
            {
              icon: Zap,
              title: 'AI Recommendations',
              desc: 'Get ranked automation candidates with estimated ROI and implementation complexity.',
            },
          ].map((card) => (
            <div
              key={card.title}
              className="rounded-xl border border-white/10 bg-white/8 p-5"
            >
              <card.icon className="h-6 w-6 text-orange-400" />
              <h3 className="mt-3 text-sm font-semibold text-white">{card.title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{card.desc}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-white/10 py-6 text-center text-xs text-slate-500">
        © {new Date().getFullYear()} Arcflare AI. All rights reserved.
      </footer>
    </div>
  )
}

function OrganizationGate() {
  return (
    <div className="flex min-h-screen flex-col bg-navy-900">
      <header className="border-b border-white/10 bg-navy-900">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-5">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/10">
              <Bot className="h-5 w-5 text-orange-300" strokeWidth={1.75} />
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-tight text-white">Arcflare</p>
              <p className="text-[11px] text-slate-400">Enterprise Intelligence</p>
            </div>
          </div>
          <UserButton
            appearance={{
              elements: {
                userButtonAvatarBox: 'h-9 w-9 ring-2 ring-white/20',
              },
            }}
          />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-lg">
          <OrganizationList
            hidePersonal
            skipInvitationScreen
            afterCreateOrganizationUrl="/#/analysis"
            afterSelectOrganizationUrl="/#/analysis"
          />
        </div>
      </main>
    </div>
  )
}

export function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { isSignedIn, isLoaded, orgId } = useClerkAuthSafe()
  const [salesforceConnectedBanner, setSalesforceConnectedBanner] = useState(false)
  const [salesforceConnectionError, setSalesforceConnectionError] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const connected = params.get('connected') === 'salesforce'
    const connectionError = params.get('connection_error')
    if (!connected && !connectionError) return

    setSalesforceConnectedBanner(connected)
    setSalesforceConnectionError(connectionError)
    params.delete('connected')
    params.delete('connection_error')
    const qs = params.toString()
    const next = `${location.pathname}${qs ? `?${qs}` : ''}${location.hash}`
    navigate(next, { replace: true })

    const timer = window.setTimeout(() => {
      setSalesforceConnectedBanner(false)
      setSalesforceConnectionError(null)
    }, 6000)
    return () => window.clearTimeout(timer)
  }, [location.hash, location.pathname, location.search, navigate])

  if (clerkEnabled && !isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy-900">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-orange-400" />
          <p className="text-sm text-slate-400">Loading...</p>
        </div>
      </div>
    )
  }

  if (clerkEnabled && !isSignedIn) {
    return <LandingPage />
  }

  if (clerkEnabled && !orgId) {
    return <OrganizationGate />
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <header className="border-b border-white/10 bg-navy-800 text-white shadow-md">
        <div className="mx-auto box-border flex max-w-[1400px] flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-6 lg:gap-10">
            <div className="flex min-w-0 items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/10">
                <Bot className="h-5 w-5 text-orange-300" strokeWidth={1.75} />
              </span>
              <div className="leading-tight">
                <p className="text-sm font-semibold tracking-tight">Arcflare</p>
                <p className="text-[11px] text-slate-300">Enterprise Intelligence</p>
              </div>
            </div>
            <nav className="hidden items-center gap-5 lg:flex lg:gap-8">
              {nav.map((item) => (
                <NavItem key={item.to} {...item} />
              ))}
            </nav>
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {clerkEnabled ? (
              <>
                <SignedIn>
                  <span className="arcflare-header-org-switcher">
                    <OrganizationSwitcher
                      hidePersonal
                      skipInvitationScreen
                      appearance={headerOrganizationSwitcherAppearance}
                      afterCreateOrganizationUrl="/#/analysis"
                      afterSelectOrganizationUrl="/#/analysis"
                      afterLeaveOrganizationUrl="/#/analysis"
                    />
                  </span>
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
        <div className="border-t border-white/10 px-4 py-2 sm:px-6 lg:hidden">
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

      {salesforceConnectedBanner && (
        <div
          className="border-b border-emerald-300 bg-emerald-50 px-6 py-3 text-center text-sm font-medium text-emerald-800"
          role="status"
        >
          Salesforce connected successfully. Metadata sync has been queued.
        </div>
      )}

      {salesforceConnectionError && (
        <div
          className="border-b border-red-300 bg-red-50 px-6 py-3 text-center text-sm font-medium text-red-800"
          role="alert"
        >
          Could not connect Salesforce: {formatSalesforceConnectionError(salesforceConnectionError)}
        </div>
      )}

      <main className="mx-auto box-border w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto box-border flex max-w-[1400px] flex-col gap-3 px-4 py-6 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} Arcflare AI. All rights reserved.</p>
        </div>
      </footer>

      <ChatLauncher />
      <ChatPanel />
    </div>
  )
}
