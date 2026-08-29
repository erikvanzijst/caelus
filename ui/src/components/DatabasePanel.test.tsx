import { render, renderHook, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiError } from '../api/client'
import type { DeploymentDatabase } from '../api/types'
import { DatabasePanel, useDatabaseDetails } from './DatabasePanel'

const getDeploymentDatabaseMock = vi.fn()

vi.mock('../api/endpoints', () => ({
  getDeploymentDatabase: (...args: unknown[]) => getDeploymentDatabaseMock(...args),
}))

const DETAILS: DeploymentDatabase = {
  host: 'caelus-tenant-pooler.caelus-tenant.svc.cluster.local',
  port: 6432,
  database: 'dpl_0f2c',
  role: 'dpl_0f2c',
  password: 'hunter2',
  password_withheld: false,
  quota_state: 'ok',
  allowance_bytes: 100 * 1024 ** 2,
  size_bytes: 0,
  measured_at: '2026-08-29T09:14:00Z',
}

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  getDeploymentDatabaseMock.mockReset()
})

describe('DatabasePanel', () => {
  it('renders the details when the deployment has a database', async () => {
    getDeploymentDatabaseMock.mockResolvedValue(DETAILS)
    renderWithQuery(<DatabasePanel userId={1} deploymentId="d1" />)

    expect(await screen.findByText(/Database \(PostgreSQL\)/)).toBeInTheDocument()
    expect(screen.getAllByText('dpl_0f2c')).toHaveLength(2)
  })

  it('renders nothing at all when the product has no relational storage', async () => {
    getDeploymentDatabaseMock.mockRejectedValue(new ApiError('no database', 404))
    const { container } = renderWithQuery(<DatabasePanel userId={1} deploymentId="d1" />)

    await waitFor(() => expect(getDeploymentDatabaseMock).toHaveBeenCalled())
    // No panel, and no placeholder implying a database exists.
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('does not retry a 404, which is a state rather than a failure', async () => {
    // Waiting for the *settled* error state is what makes this meaningful: a
    // retried query does not reach it for at least one backoff, which is
    // longer than waitFor's default. Asserting the call count alone would
    // pass while the query was still retrying in the background.
    getDeploymentDatabaseMock.mockRejectedValue(new ApiError('no database', 404))
    const client = new QueryClient({ defaultOptions: { queries: { retry: 3 } } })
    const { result } = renderHook(() => useDatabaseDetails(1, 'd1'), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(getDeploymentDatabaseMock).toHaveBeenCalledTimes(1)
  })

  it('does retry an error that is not a 404', async () => {
    // Only the 404 is a state; anything else is a failure worth retrying.
    // The predicate keeps returning true, so the retry is unbounded -- the
    // same shape as useSftpCredentials -- hence the unmount rather than an
    // exact count.
    getDeploymentDatabaseMock.mockRejectedValue(new ApiError('boom', 500))
    const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } })
    const { unmount } = renderHook(() => useDatabaseDetails(1, 'd1'), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    })

    await waitFor(() =>
      expect(getDeploymentDatabaseMock.mock.calls.length).toBeGreaterThan(1),
    )
    unmount()
    client.clear()
  })

  it('writes no secret to browser storage or the address bar', async () => {
    getDeploymentDatabaseMock.mockResolvedValue(DETAILS)
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    renderWithQuery(<DatabasePanel userId={1} deploymentId="d1" />)

    await screen.findByText(/Database \(PostgreSQL\)/)
    expect(setItem).not.toHaveBeenCalled()
    expect(window.location.href).not.toContain('hunter2')
    setItem.mockRestore()
  })
})
