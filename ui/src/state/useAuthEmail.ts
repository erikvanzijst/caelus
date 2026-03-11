import { useEffect, useState } from 'react'

const HEADERS_KEY = 'caelus.auth.headers'

export type AuthHeaders = Record<string, string>

export function getStoredAuthHeaders(): AuthHeaders {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(HEADERS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as AuthHeaders
    }
  } catch {
    // corrupted value — ignore
  }
  return {}
}

function getEmailFromHeaders(headers: AuthHeaders): string {
  return headers['X-Auth-Request-Email'] ?? ''
}

export function useAuthHeaders() {
  const [headers, setHeaders] = useState<AuthHeaders>(getStoredAuthHeaders)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (Object.keys(headers).length > 0) {
      window.localStorage.setItem(HEADERS_KEY, JSON.stringify(headers))
    } else {
      window.localStorage.removeItem(HEADERS_KEY)
    }
  }, [headers])

  const email = getEmailFromHeaders(headers)

  const setEmail = (newEmail: string) => {
    if (newEmail) {
      setHeaders({ 'X-Auth-Request-Email': newEmail })
    } else {
      setHeaders({})
    }
  }

  return { headers, setHeaders, email, setEmail }
}
