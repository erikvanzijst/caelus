import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiError } from '../api/client'
import type { Deployment, DeploymentDatabase } from '../api/types'
import { DeploymentCard } from './DeploymentCard'

const getDeploymentDatabaseMock = vi.fn()
const getDeploymentSftpMock = vi.fn()

vi.mock('../api/endpoints', () => ({
  getDeploymentDatabase: (...args: unknown[]) => getDeploymentDatabaseMock(...args),
  getDeploymentSftp: (...args: unknown[]) => getDeploymentSftpMock(...args),
}))

const DETAILS: DeploymentDatabase = {
  host: 'pooler.internal',
  port: 6432,
  database: 'dpl_0f2c',
  role: 'dpl_0f2c',
  password: 'hunter2',
  password_withheld: false,
  quota_state: 'ok',
  allowance_bytes: 100 * 1024 ** 2,
  size_bytes: null,
  measured_at: null,
}

function deployment(status: Deployment['status']): Deployment {
  return {
    id: 'd1',
    desired_template_id: 1,
    hostname: 'app.example.test',
    user_id: 1,
    created_at: '2026-08-01T00:00:00Z',
    user: { id: 1, email: 'o@example.com', is_admin: false, created_at: '2026-08-01T00:00:00Z' },
    desired_template: { id: 1 } as Deployment['desired_template'],
    name: 'app',
    namespace: 'ns',
    status,
    generation: 2,
  }
}

function renderCard(status: Deployment['status']) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (dep: Deployment) => (
    <QueryClientProvider client={client}>
      <DeploymentCard
        deployment={dep}
        userId={1}
        deletePending={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />
    </QueryClientProvider>
  )
  const result = render(ui(deployment(status)))
  return { ...result, settle: () => result.rerender(ui(deployment('ready'))) }
}

beforeEach(() => {
  getDeploymentDatabaseMock.mockReset()
  getDeploymentSftpMock.mockReset()
  getDeploymentSftpMock.mockRejectedValue(new ApiError('no sftp', 404))
})

describe('DeploymentCard database action', () => {
  it('offers no Database action when the deployment has no database', async () => {
    getDeploymentDatabaseMock.mockRejectedValue(new ApiError('no database', 404))
    renderCard('ready')

    await waitFor(() => expect(getDeploymentDatabaseMock).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /database/i })).not.toBeInTheDocument()
  })

  it('picks the details up when a transitional deployment settles', async () => {
    // Provisioning: the database is not there yet, which is the deployment's
    // own state rather than a state of the database.
    getDeploymentDatabaseMock.mockRejectedValue(new ApiError('no database', 404))
    const { settle } = renderCard('provisioning')

    await waitFor(() => expect(getDeploymentDatabaseMock).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /database/i })).not.toBeInTheDocument()

    // It settles, and the panel re-requests without the reader reloading.
    getDeploymentDatabaseMock.mockResolvedValue(DETAILS)
    settle()

    expect(await screen.findByRole('button', { name: /database/i })).toBeInTheDocument()
  })
})
