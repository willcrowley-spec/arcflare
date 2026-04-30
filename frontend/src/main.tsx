import { StrictMode, useEffect, useRef, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import { setApiTokenGetter } from '@/api/client'
import { useChatStore } from '@/stores/chatStore'
import { useConnectionStore } from '@/stores/connectionStore'

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || ''
export const clerkEnabled = !!clerkPubKey

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

function ApiTokenBridge() {
  const { getToken, isSignedIn, orgId } = useAuth()
  const lastOrgIdRef = useRef<string | null | undefined>(undefined)

  useEffect(() => {
    const resetOrgScopedState = () => {
      queryClient.clear()
      useConnectionStore.getState().reset()
      useChatStore.getState().reset()
    }

    if (!isSignedIn || !orgId) {
      setApiTokenGetter(null)
      if (lastOrgIdRef.current !== undefined && lastOrgIdRef.current !== null) {
        resetOrgScopedState()
      }
      lastOrgIdRef.current = orgId ?? null
      return
    }

    if (lastOrgIdRef.current !== undefined && lastOrgIdRef.current !== orgId) {
      resetOrgScopedState()
    }
    lastOrgIdRef.current = orgId
    void getToken({ organizationId: orgId, skipCache: true })
    setApiTokenGetter(() => getToken({ organizationId: orgId }))
    return () => setApiTokenGetter(null)
  }, [getToken, isSignedIn, orgId])

  return null
}

function AuthShell({ children }: { children: ReactNode }) {
  if (!clerkEnabled) return <>{children}</>
  return (
    <ClerkProvider publishableKey={clerkPubKey}>
      <ApiTokenBridge />
      {children}
    </ClerkProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthShell>
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <App />
        </HashRouter>
      </QueryClientProvider>
    </AuthShell>
  </StrictMode>,
)
