import { useEffect, useState } from 'react'

const STORAGE_KEY = 'caelus.auth.email'

export function getStoredEmail() {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(STORAGE_KEY) ?? ''
}

export function useAuthEmail() {
  const [email, setEmail] = useState(getStoredEmail)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (email) {
      window.localStorage.setItem(STORAGE_KEY, email)
    } else {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }, [email])

  return { email, setEmail }
}
