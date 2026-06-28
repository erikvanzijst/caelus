import { useCallback, useState } from 'react'
import { useAuth } from '../../state/AuthContext'

/** True when running behind Keycloak/oauth2-proxy (auth handled by proxy). */
const proxyAuth = Boolean(import.meta.env.VITE_KEYCLOAK_ACCOUNT_URL)

/**
 * Drives the landing page's primary call-to-action.
 *
 * - In production (behind oauth2-proxy/Keycloak): kick off the hosted
 *   sign-in/registration flow, returning to the root afterwards.
 * - In local dev (no proxy): open the email dialog so the SPA can attach an
 *   identity to requests, mirroring the existing dev login behaviour.
 */
export function useStartSignup() {
  const { setEmail } = useAuth()
  const [dialogOpen, setDialogOpen] = useState(false)

  const start = useCallback(() => {
    if (proxyAuth) {
      const rd = encodeURIComponent(window.location.origin + '/')
      // oauth2-proxy initiates the Keycloak login/registration flow here.
      window.location.href = `/oauth2/start?rd=${rd}`
    } else {
      setDialogOpen(true)
    }
  }, [])

  return { start, dialogOpen, setDialogOpen, setEmail }
}

export default useStartSignup
