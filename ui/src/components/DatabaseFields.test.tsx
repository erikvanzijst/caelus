import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { DeploymentDatabase } from '../api/types'
import { DatabaseFields } from './DatabaseFields'

const PASSWORD = 'p@ss/w:rd?#[]&=+ 90%'

function details(overrides: Partial<DeploymentDatabase> = {}): DeploymentDatabase {
  return {
    host: 'caelus-tenant-pooler.caelus-tenant.svc.cluster.local',
    port: 6432,
    database: 'dpl_0f2c',
    role: 'dpl_0f2c',
    password: PASSWORD,
    password_withheld: false,
    quota_state: 'ok',
    allowance_bytes: 100 * 1024 ** 2,
    size_bytes: 42 * 1024 ** 2,
    measured_at: '2026-08-29T09:14:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
})

describe('DatabaseFields', () => {
  it('shows the database and role', () => {
    render(<DatabaseFields database={details()} />)
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.getByText('Role')).toBeInTheDocument()
    // The platform names both after the deployment, so one string fills both.
    expect(screen.getAllByText('dpl_0f2c')).toHaveLength(2)
  })

  it('shows no address and no connection URL', () => {
    const { container } = render(<DatabaseFields database={details()} />)
    expect(container.textContent).not.toContain('caelus-tenant-pooler')
    expect(container.textContent).not.toContain('6432')
    expect(container.textContent).not.toContain('postgresql://')
  })

  it('masks the password until it is revealed', () => {
    const { container } = render(<DatabaseFields database={details()} />)
    expect(container.textContent).not.toContain(PASSWORD)

    fireEvent.click(screen.getByRole('button', { name: /show password/i }))
    expect(screen.getByText(PASSWORD)).toBeInTheDocument()
  })

  it('copies the password without revealing it', () => {
    const { container } = render(<DatabaseFields database={details()} />)
    fireEvent.click(screen.getByRole('button', { name: /copy password/i }))

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(PASSWORD)
    expect(container.textContent).not.toContain(PASSWORD)
  })

  it('says where the database can be reached from', () => {
    render(<DatabaseFields database={details()} />)
    expect(screen.getByText(/not reachable from this computer/i)).toBeInTheDocument()
    expect(screen.getByText(/reachable from your running app/i)).toBeInTheDocument()
  })

  it('shows usage as a percentage, with the figures behind it', () => {
    render(<DatabaseFields database={details()} />)
    expect(screen.getByText('42% (42 MB of 100 MB)')).toBeInTheDocument()
    expect(screen.getByText(/measured/i)).toBeInTheDocument()
  })

  it('does not round a non-empty database down to nothing', () => {
    render(<DatabaseFields database={details({ size_bytes: 64 * 1024 })} />)
    expect(screen.getByText('<1% (64 KB of 100 MB)')).toBeInTheDocument()
  })

  it('reports a database past its allowance as over 100%', () => {
    render(
      <DatabaseFields
        database={details({ size_bytes: 142 * 1024 ** 2, quota_state: 'readonly' })}
      />,
    )
    expect(screen.getByText('142% (142 MB of 100 MB)')).toBeInTheDocument()
  })

  it('says the size is not yet known rather than showing zero', () => {
    render(<DatabaseFields database={details({ size_bytes: null, measured_at: null })} />)
    expect(screen.getByText(/not yet measured/i)).toBeInTheDocument()
    expect(screen.queryByText(/^0 B of/)).not.toBeInTheDocument()
  })

  it('distinguishes a database measured at zero', () => {
    render(<DatabaseFields database={details({ size_bytes: 0 })} />)
    expect(screen.getByText('0% (0 B of 100 MB)')).toBeInTheDocument()
    expect(screen.queryByText(/not yet measured/i)).not.toBeInTheDocument()
  })

  it('explains a read-only database in terms of its consequence', () => {
    render(<DatabaseFields database={details({ quota_state: 'readonly' })} />)
    expect(screen.getByText(/every write is rejected/i)).toBeInTheDocument()
  })

  it('explains a suspended database in terms of its consequence', () => {
    render(<DatabaseFields database={details({ quota_state: 'blocked' })} />)
    expect(screen.getByText(/cannot connect to it at all/i)).toBeInTheDocument()
  })

  it('renders a healthy database without either alert', () => {
    render(<DatabaseFields database={details()} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('states a withheld password rather than failing', () => {
    render(
      <DatabaseFields database={details({ password: null, password_withheld: true })} />,
    )
    expect(screen.getByText(/withheld/i)).toBeInTheDocument()
    // No reveal affordance that could not work, and no error.
    expect(screen.queryByRole('button', { name: /show password/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    // The rest of the details are still shown.
    expect(screen.getAllByText('dpl_0f2c')).toHaveLength(2)
    expect(screen.getByText('42% (42 MB of 100 MB)')).toBeInTheDocument()
  })
})
