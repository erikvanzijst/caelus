import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PlanTemplateTabs } from './PlanTemplateTabs'
import { createPlanTemplate } from '../api/endpoints'
import type { Plan, PlanTemplateVersion } from '../api/types'

vi.mock('../api/endpoints', () => ({
  createPlanTemplate: vi.fn().mockResolvedValue({ id: 99 }),
  updatePlan: vi.fn().mockResolvedValue({}),
}))

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const plan: Plan = {
  id: 1,
  name: 'Basic',
  product_id: 1,
  template_id: 10,
  sort_order: 1000,
  created_at: '2026-01-01T00:00:00Z',
}

const template: PlanTemplateVersion = {
  id: 10,
  plan_id: 1,
  price_cents: 300,
  billing_interval: 'monthly',
  storage_bytes: 10737418240,
  database_bytes: 1073741824,
  description: null,
  created_at: '2026-01-01T00:00:00Z',
}

describe('PlanTemplateTabs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the database allowance beside the storage allowance', () => {
    renderWithQuery(
      <PlanTemplateTabs plan={plan} templates={[template]} onError={vi.fn()} />,
    )
    expect(screen.getByText('Storage')).toBeInTheDocument()
    expect(screen.getByText('10.0 GB')).toBeInTheDocument()
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.getByText('1.0 GB')).toBeInTheDocument()
  })

  it('reports a plan with no database allowance as none', () => {
    renderWithQuery(
      <PlanTemplateTabs
        plan={plan}
        templates={[{ ...template, database_bytes: null }]}
        onError={vi.fn()}
      />,
    )
    expect(screen.getByText('None')).toBeInTheDocument()
  })

  it('submits the database allowance in bytes', async () => {
    renderWithQuery(
      <PlanTemplateTabs plan={plan} templates={[]} onError={vi.fn()} />,
    )

    fireEvent.change(screen.getByLabelText('Price (€)'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Database (MB)'), { target: { value: '100' } })
    fireEvent.click(screen.getByText('Create template'))

    // react-query runs the mutation off the click, so wait for the call.
    await waitFor(() =>
      expect(createPlanTemplate).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ price_cents: 300, database_bytes: 104857600 }),
      ),
    )
  })

  it('carries the previous version allowance into a new one', () => {
    renderWithQuery(
      <PlanTemplateTabs plan={plan} templates={[template]} onError={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('tab', { name: /New/ }))
    expect(screen.getByLabelText('Database (MB)')).toHaveValue(1024)
  })

  it('omits an allowance the operator leaves empty', async () => {
    renderWithQuery(
      <PlanTemplateTabs plan={plan} templates={[]} onError={vi.fn()} />,
    )

    fireEvent.change(screen.getByLabelText('Price (€)'), { target: { value: '0' } })
    fireEvent.click(screen.getByText('Create template'))

    await waitFor(() =>
      expect(createPlanTemplate).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ database_bytes: null }),
      ),
    )
  })
})
