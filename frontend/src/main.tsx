import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import { setApiTokenGetter } from '@/api/client'

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || ''
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

function ApiTokenBridge() {
  const { getToken, isSignedIn } = useAuth()

  useEffect(() => {
    if (!isSignedIn) {
      setApiTokenGetter(null)
      return
    }
    setApiTokenGetter(() => getToken())
    return () => setApiTokenGetter(null)
  }, [getToken, isSignedIn])

  return null
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={clerkPubKey}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ApiTokenBridge />
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
)
