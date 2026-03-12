import { getStoredAuthHeaders } from '../state/useAuthEmail'

const envUrl = import.meta.env.VITE_API_URL as string | undefined

export const API_URL = envUrl ?? '/api'

/** Resolve an absolute API path (e.g. /api/static/icons/foo.png) to a full URL. */
export function resolveApiPath(absolutePath: string): string {
  const origin = API_URL.replace(/\/api\/?$/, '')
  return `${origin}${absolutePath}`
}

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
  options: RequestInit = {},
): Promise<T> {
  const { headers, ...rest } = options
  const authHeaders = getStoredAuthHeaders()
  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
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

export async function requestMultipart<T>(
  path: string,
  payload: object,
  file?: { field: string; file: File | Blob },
  options: RequestInit = {},
): Promise<T> {
  const { headers, ...rest } = options
  const authHeaders = getStoredAuthHeaders()
  const formData = new FormData()
  formData.append('payload', JSON.stringify(payload))
  if (file) {
    formData.append(file.field, file.file)
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    method: 'POST',
    body: formData,
    headers: {
      ...authHeaders,
      ...(headers ?? {}),
    },
  })

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
