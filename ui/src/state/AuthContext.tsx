import { createContext, useContext, useCallback, useEffect, useState } from 'react'
import type { PropsWithChildren } from 'react'
import type { User } from '../api/types'
import { getMe } from '../api/endpoints'
import { useAuthHeaders, getStoredAuthHeaders } from './useAuthEmail'

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
      sessionStorage.removeItem('caelus.auth.reloading')
    } catch {
      // In production (no localStorage auth headers), a failed /api/me means
      // the session cookie is missing or invalid. Reload to trigger Traefik's
      // forward-auth middleware which will redirect to Keycloak login.
      // Guard with sessionStorage to prevent infinite reloads if the page is
      // served from a stale browser cache.
      const isProduction = Object.keys(getStoredAuthHeaders()).length === 0
      const reloadKey = 'caelus.auth.reloading'
      if (isProduction && !sessionStorage.getItem(reloadKey)) {
        sessionStorage.setItem(reloadKey, '1')
        window.location.reload()
        return
      }
      sessionStorage.removeItem(reloadKey)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  // On mount and whenever email changes, try /api/me
  useEffect(() => {
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
