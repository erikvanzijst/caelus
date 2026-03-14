import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { DeployDialog } from './DeployDialog'
import type { Product } from '../api/types'

const listTemplatesMock = vi.fn()
const createDeploymentMock = vi.fn()
const checkHostnameMock = vi.fn()
const listDomainsMock = vi.fn()

vi.mock('../api/endpoints', () => ({
  listTemplates: (...args: unknown[]) => listTemplatesMock(...args),
  createDeployment: (...args: unknown[]) => createDeploymentMock(...args),
  checkHostname: (...args: unknown[]) => checkHostnameMock(...args),
  listDomains: (...args: unknown[]) => listDomainsMock(...args),
}))

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const helloWorld: Product = {
  id: 1,
  name: 'Hello World',
  description: 'The obligatory hello world',
  template_id: 10,
  icon_url: null,
  created_at: '2026-01-01T00:00:00Z',
}

const helloTemplate = {
  id: 10,
  product_id: 1,
  chart_ref: 'oci://registry/hello',
  chart_version: '0.1.0',
  default_values_json: null,
  values_schema_json: {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    type: 'object',
    properties: {
      hostname: {
        title: 'hostname',
        type: 'string',
        minLength: 1,
      },
    },
    required: ['hostname'],
    additionalProperties: false,
  },
  created_at: '2026-01-01T00:00:00Z',
}

describe('DeployDialog', () => {
  it('renders product name and description in the header', async () => {
    listTemplatesMock.mockResolvedValue([helloTemplate])
    listDomainsMock.mockResolvedValue([])

    renderWithQuery(
      <DeployDialog product={helloWorld} userId={1} onClose={vi.fn()} />,
    )

    expect(screen.getByText('Hello World')).toBeInTheDocument()
    expect(screen.getByText('The obligatory hello world')).toBeInTheDocument()
  })

  it('shows Cancel and disabled Launch buttons', async () => {
    listTemplatesMock.mockResolvedValue([helloTemplate])
    listDomainsMock.mockResolvedValue([])

    renderWithQuery(
      <DeployDialog product={helloWorld} userId={1} onClose={vi.fn()} />,
    )

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Launch' })).toBeDisabled()
    })
  })

  it('calls onClose when Cancel is clicked', async () => {
    listTemplatesMock.mockResolvedValue([helloTemplate])
    listDomainsMock.mockResolvedValue([])
    const onClose = vi.fn()

    renderWithQuery(
      <DeployDialog product={helloWorld} userId={1} onClose={onClose} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('shows warning when product has no template', async () => {
    const noTemplate: Product = { ...helloWorld, template_id: null }
    listTemplatesMock.mockResolvedValue([])
    listDomainsMock.mockResolvedValue([])

    renderWithQuery(
      <DeployDialog product={noTemplate} userId={1} onClose={vi.fn()} />,
    )

    await waitFor(() => {
      expect(screen.getByText('This product has no template configured yet.')).toBeInTheDocument()
    })
  })

  it('enables Launch when hostname is valid and submits deployment', async () => {
    listTemplatesMock.mockResolvedValue([helloTemplate])
    listDomainsMock.mockResolvedValue([])
    checkHostnameMock.mockResolvedValue({ fqdn: 'test.example.com', usable: true, reason: null })
    createDeploymentMock.mockResolvedValue({ id: 1 })
    const onClose = vi.fn()

    renderWithQuery(
      <DeployDialog product={helloWorld} userId={42} onClose={onClose} />,
    )

    // Wait for the template query to resolve and the form to render
    await waitFor(() => {
      expect(screen.getByText('Configure application values:')).toBeInTheDocument()
    })

    const hostnameInput = screen.getByRole('textbox', { name: /hostname/i })
    fireEvent.change(hostnameInput, { target: { value: 'test.example.com' } })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Launch' })).toBeEnabled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Launch' }))

    await waitFor(() => {
      expect(createDeploymentMock).toHaveBeenCalledWith(42, {
        desired_template_id: 10,
        user_values_json: { hostname: 'test.example.com' },
      })
    })

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('shows error alert on deployment failure', async () => {
    listTemplatesMock.mockResolvedValue([helloTemplate])
    listDomainsMock.mockResolvedValue([])
    checkHostnameMock.mockResolvedValue({ fqdn: 'test.example.com', usable: true, reason: null })
    createDeploymentMock.mockRejectedValue(new Error('Server error'))

    renderWithQuery(
      <DeployDialog product={helloWorld} userId={1} onClose={vi.fn()} />,
    )

    await waitFor(() => {
      expect(screen.getByText('Configure application values:')).toBeInTheDocument()
    })

    const hostnameInput = screen.getByRole('textbox', { name: /hostname/i })
    fireEvent.change(hostnameInput, { target: { value: 'test.example.com' } })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Launch' })).toBeEnabled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Launch' }))

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })
})
