import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestJson } from './client'

describe('requestJson error mapping', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('normalizes FastAPI validation array detail into readable message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 422,
        ok: false,
        statusText: 'Unprocessable Content',
        json: vi.fn().mockResolvedValue({
          detail: [
            { msg: 'Field required' },
            { msg: 'Another error' },
          ],
        }),
      }),
    )

    await expect(requestJson('/users/3/deployments')).rejects.toThrow(
      'Field required; Another error',
    )
  })

  it('falls back to status text when response body is not json on error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 500,
        ok: false,
        statusText: 'Internal Server Error',
        json: vi.fn().mockRejectedValue(new Error('invalid json')),
      }),
    )

    await expect(requestJson('/products/4/templates')).rejects.toThrow(
      'Internal Server Error',
    )
  })
})
