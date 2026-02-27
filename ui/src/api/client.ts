const envUrl = import.meta.env.VITE_API_URL as string | undefined

export const API_URL = envUrl ?? '/api'

function toErrorMessage(detail: unknown, fallback: string) {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') {
          return item.msg
        }
        return null
      })
      .filter(Boolean) as string[]
    if (messages.length > 0) return messages.join('; ')
  }
  return fallback
}

export async function requestJson<T>(
  path: string,
  options: RequestInit & { authEmail?: string } = {},
): Promise<T> {
  const { authEmail, headers, ...rest } = options
  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(authEmail ? { 'x-auth-request-email': authEmail } : {}),
      ...(headers ?? {}),
    },
  })

  if (response.status === 204) {
    return null as T
  }

  let data: ({ detail?: unknown } & T) | null = null
  try {
    data = (await response.json()) as { detail?: unknown } & T
  } catch {
    if (!response.ok) {
      throw new Error(response.statusText || 'Request failed')
    }
    throw new Error('Invalid JSON response')
  }
  if (!response.ok) {
    throw new Error(toErrorMessage(data?.detail, response.statusText || 'Request failed'))
  }
  return data as T
}
