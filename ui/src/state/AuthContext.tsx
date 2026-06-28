import { createContext, useContext, useCallback, useEffect, useState } from 'react'
import type { PropsWithChildren } from 'react'
import type { User } from '../api/types'
import { getMe } from '../api/endpoints'
import { useAuthHeaders } from './useAuthEmail'

/** True when running behind Keycloak/oauth2-proxy (auth handled by proxy). */
const proxyAuth = Boolean(import.meta.env.VITE_KEYCLOAK_ACCOUNT_URL)

interface AuthState {
  user: User | null
  loading: boolean
  email: string
  setEmail: (email: string) => void
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  email: '',
  setEmail: () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: PropsWithChildren) {
  const { email, setEmail } = useAuthHeaders()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const tryGetMe = useCallback(async () => {
    setLoading(true)
    try {
      const me = await getMe()
      setUser(me)
    } catch {
      // Anonymous, or an expired session: render the public landing page.
      // We no longer force a reload into Keycloak here — the landing serves
      // at the same root path, and login is initiated explicitly via the
      // landing CTA (see useStartSignup). In production this relies on the
      // edge no longer rewriting anonymous 401s into redirects; in local
      // dev there is no proxy and /api/me simply 404s without a header.
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  // On mount and whenever email changes, try /api/me.
  // Without proxy auth, skip the call when no email is set — show the dialog.
  useEffect(() => {
    if (!proxyAuth && !email) {
      setUser(null)
      setLoading(false)
      return
    }
    tryGetMe()
  }, [email, tryGetMe])

  const handleSetEmail = useCallback(
    (newEmail: string) => {
      setEmail(newEmail)
      // The useEffect above will re-trigger tryGetMe when email changes
    },
    [setEmail],
  )

  return (
    <AuthContext.Provider value={{ user, loading, email, setEmail: handleSetEmail }}>
      {children}
    </AuthContext.Provider>
  )
}
