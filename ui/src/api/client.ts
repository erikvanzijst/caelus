const envUrl = import.meta.env.VITE_API_URL as string | undefined

export const API_URL = envUrl ?? 'http://localhost:8000'

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

  const data = (await response.json()) as { detail?: string } & T
  if (!response.ok) {
    throw new Error(data?.detail || response.statusText)
  }
  return data as T
}
