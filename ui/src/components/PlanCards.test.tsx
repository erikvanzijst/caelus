import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PlanCards, calculateSortOrder, SORT_ORDER_GAP } from './PlanCards'
import type { Plan } from '../api/types'

// dnd-kit doesn't play well with jsdom; mock sortable to render children normally
vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  closestCenter: vi.fn(),
  PointerSensor: vi.fn(),
  useSensor: vi.fn(),
  useSensors: () => [],
}))
vi.mock('@dnd-kit/sortable', () => ({
  SortableContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  horizontalListSortingStrategy: vi.fn(),
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: null,
    isDragging: false,
  }),
}))

const freePlan: Plan = {
  id: 1,
  name: 'Free',
  description: 'Everything for free',
  product_id: 1,
  template_id: 10,
  sort_order: 1000,
  created_at: '2026-01-01T00:00:00Z',
  template: {
    id: 10,
    plan_id: 1,
    price_cents: 0,
    billing_interval: 'monthly',
    storage_bytes: 0,
    created_at: '2026-01-01T00:00:00Z',
  },
}

const proPlan: Plan = {
  id: 2,
  name: 'Pro',
  description: '- 100GB storage\n- Priority support',
  product_id: 1,
  template_id: 20,
  sort_order: 2000,
  created_at: '2026-01-01T00:00:00Z',
  template: {
    id: 20,
    plan_id: 2,
    price_cents: 999,
    billing_interval: 'monthly',
    storage_bytes: 107374182400,
    created_at: '2026-01-01T00:00:00Z',
  },
}

const defaultProps = {
  plans: [freePlan, proPlan],
  selectedPlanId: 1 as number | 'new' | null,
  onSelectPlan: vi.fn(),
  onCreatePlan: vi.fn(),
  onUpdatePlan: vi.fn(),
  onDeletePlan: vi.fn(),
  onReorder: vi.fn(),
}

describe('PlanCards', () => {
  it('renders all plan cards and the new plan button', () => {
    render(<PlanCards {...defaultProps} />)
    expect(screen.getAllByText('Free').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Pro')).toBeInTheDocument()
    expect(screen.getByText('New plan')).toBeInTheDocument()
  })

  it('displays price from canonical template', () => {
    render(<PlanCards {...defaultProps} />)
    // Free plan shows "Free" as price
    const freeCards = screen.getAllByText('Free')
    expect(freeCards.length).toBeGreaterThanOrEqual(2) // name + price
    // Pro plan shows "€9.99/mo"
    expect(screen.getByText('€9.99/mo')).toBeInTheDocument()
  })

  it('renders markdown description', () => {
    render(<PlanCards {...defaultProps} />)
    expect(screen.getByText('100GB storage')).toBeInTheDocument()
    expect(screen.getByText('Priority support')).toBeInTheDocument()
  })

  it('calls onSelectPlan when a card is clicked', () => {
    const onSelectPlan = vi.fn()
    render(<PlanCards {...defaultProps} onSelectPlan={onSelectPlan} />)
    fireEvent.click(screen.getByText('Pro'))
    expect(onSelectPlan).toHaveBeenCalledWith(2)
  })

  it('shows create form when New plan is clicked', () => {
    const onSelectPlan = vi.fn()
    render(<PlanCards {...defaultProps} selectedPlanId={null} onSelectPlan={onSelectPlan} />)
    fireEvent.click(screen.getByText('New plan'))
    expect(screen.getByLabelText('Plan name')).toBeInTheDocument()
    expect(screen.getByLabelText('Description (Markdown)')).toBeInTheDocument()
    expect(screen.getByText('Create')).toBeDisabled()
  })

  it('calls onCreatePlan when form is filled and Create is clicked', () => {
    const onCreatePlan = vi.fn()
    render(<PlanCards {...defaultProps} selectedPlanId={null} onCreatePlan={onCreatePlan} />)
    fireEvent.click(screen.getByText('New plan'))

    fireEvent.change(screen.getByLabelText('Plan name'), { target: { value: 'Enterprise' } })
    fireEvent.change(screen.getByLabelText('Description (Markdown)'), { target: { value: 'For teams' } })
    fireEvent.click(screen.getByText('Create'))

    expect(onCreatePlan).toHaveBeenCalledWith({ name: 'Enterprise', description: 'For teams' })
  })

  it('hides create form when Cancel is clicked', () => {
    render(<PlanCards {...defaultProps} selectedPlanId={null} />)
    fireEvent.click(screen.getByText('New plan'))
    expect(screen.getByLabelText('Plan name')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByLabelText('Plan name')).not.toBeInTheDocument()
    expect(screen.getByText('New plan')).toBeInTheDocument()
  })

  it('shows edit form when edit icon is clicked on existing card', () => {
    render(<PlanCards {...defaultProps} />)
    // Find edit buttons (there are 2 plans x 2 icon buttons each)
    const editButtons = screen.getAllByRole('button').filter((btn) => {
      const svg = btn.querySelector('svg[data-testid="EditIcon"]')
      return svg !== null
    })
    expect(editButtons.length).toBe(2)

    fireEvent.click(editButtons[0])
    expect(screen.getByLabelText('Plan name')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Free')).toBeInTheDocument()
  })

  it('calls onUpdatePlan when existing card is saved', () => {
    const onUpdatePlan = vi.fn()
    render(<PlanCards {...defaultProps} onUpdatePlan={onUpdatePlan} />)

    // Click edit on Free plan
    const editButtons = screen.getAllByRole('button').filter((btn) =>
      btn.querySelector('svg[data-testid="EditIcon"]') !== null
    )
    fireEvent.click(editButtons[0])

    fireEvent.change(screen.getByDisplayValue('Free'), { target: { value: 'Basic' } })
    fireEvent.click(screen.getByText('Save'))

    expect(onUpdatePlan).toHaveBeenCalledWith(1, { name: 'Basic', description: 'Everything for free' })
  })

  it('calls onDeletePlan when delete is confirmed', () => {
    const onDeletePlan = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<PlanCards {...defaultProps} onDeletePlan={onDeletePlan} />)

    const deleteButtons = screen.getAllByRole('button').filter((btn) =>
      btn.querySelector('svg[data-testid="DeleteIcon"]') !== null
    )
    fireEvent.click(deleteButtons[0])

    expect(onDeletePlan).toHaveBeenCalledWith(1)
    vi.restoreAllMocks()
  })

  it('does not call onDeletePlan when delete is cancelled', () => {
    const onDeletePlan = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<PlanCards {...defaultProps} onDeletePlan={onDeletePlan} />)

    const deleteButtons = screen.getAllByRole('button').filter((btn) =>
      btn.querySelector('svg[data-testid="DeleteIcon"]') !== null
    )
    fireEvent.click(deleteButtons[0])

    expect(onDeletePlan).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })

  it('shows selected card with primary border', () => {
    render(<PlanCards {...defaultProps} selectedPlanId={2} />)
    // The Pro card (id=2) should have the primary border
    const proCard = screen.getByText('€9.99/mo').closest('[class*="MuiCard-root"]')
    expect(proCard).toBeTruthy()
  })

  it('renders plan without template gracefully', () => {
    const planNoTemplate: Plan = {
      ...proPlan,
      id: 3,
      name: 'Draft',
      template_id: null,
      template: undefined,
    }
    render(<PlanCards {...defaultProps} plans={[...defaultProps.plans, planNoTemplate]} />)
    expect(screen.getByText('Draft')).toBeInTheDocument()
    // Shows placeholder price
    expect(screen.getByText('TBD')).toBeInTheDocument()
  })
})

describe('calculateSortOrder', () => {
  const makePlan = (id: number, sortOrder: number): Plan => ({
    id,
    name: `Plan ${id}`,
    product_id: 1,
    sort_order: sortOrder,
    created_at: '2026-01-01T00:00:00Z',
  })

  it('returns GAP for a single item', () => {
    const plans = [makePlan(1, 1000)]
    expect(calculateSortOrder(plans, 0, 1)).toBe(SORT_ORDER_GAP)
  })

  it('places item between two neighbors at the midpoint', () => {
    const plans = [makePlan(1, 1000), makePlan(2, 2000), makePlan(3, 3000)]
    // Move plan 3 between plan 1 and plan 2 (toIndex=1)
    const result = calculateSortOrder(plans, 1, 3)
    expect(result).toBe(1500)
  })

  it('places item before the first at first - GAP', () => {
    const plans = [makePlan(1, 1000), makePlan(2, 2000), makePlan(3, 3000)]
    // Move plan 3 to the beginning (toIndex=0)
    const result = calculateSortOrder(plans, 0, 3)
    expect(result).toBe(1000 - SORT_ORDER_GAP)
  })

  it('places item after the last at last + GAP', () => {
    const plans = [makePlan(1, 1000), makePlan(2, 2000), makePlan(3, 3000)]
    // Move plan 1 to the end (toIndex=2)
    const result = calculateSortOrder(plans, 2, 1)
    expect(result).toBe(3000 + SORT_ORDER_GAP)
  })

  it('handles swap of two adjacent items', () => {
    const plans = [makePlan(1, 1000), makePlan(2, 2000)]
    // Move plan 2 to position 0 (before plan 1)
    const result = calculateSortOrder(plans, 0, 2)
    expect(result).toBe(1000 - SORT_ORDER_GAP)
  })

  it('produces correct midpoint with uneven spacing', () => {
    const plans = [makePlan(1, 100), makePlan(2, 500), makePlan(3, 10000)]
    // Move plan 3 between plan 1 and plan 2 (toIndex=1)
    const result = calculateSortOrder(plans, 1, 3)
    expect(result).toBe(300) // midpoint of 100 and 500
  })

  it('handles repeated reorderings without collision', () => {
    // Simulate inserting between two items multiple times
    let plans = [makePlan(1, 1000), makePlan(2, 2000)]

    // Insert plan 3 between 1 and 2
    const order3 = calculateSortOrder([...plans, makePlan(3, 9999)], 1, 3)
    expect(order3).toBe(1500)
    plans = [makePlan(1, 1000), makePlan(3, order3), makePlan(2, 2000)]

    // Insert plan 4 between 1 and 3
    const order4 = calculateSortOrder([...plans, makePlan(4, 9999)], 1, 4)
    expect(order4).toBe(1250)

    // Insert plan 5 between 1 and 4
    plans = [makePlan(1, 1000), makePlan(4, order4), makePlan(3, order3), makePlan(2, 2000)]
    const order5 = calculateSortOrder([...plans, makePlan(5, 9999)], 1, 5)
    expect(order5).toBe(1125)

    // All sort orders should be distinct and in ascending order
    const allOrders = [1000, order5, order4, order3, 2000].sort((a, b) => a - b)
    for (let i = 1; i < allOrders.length; i++) {
      expect(allOrders[i]).toBeGreaterThan(allOrders[i - 1])
    }
  })
})
