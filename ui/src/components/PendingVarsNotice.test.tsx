import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PendingVarsNotice } from '../components/PendingVarsNotice'

describe('PendingVarsNotice', () => {
  it('renders nothing when nothing is pending', () => {
    const { container } = render(
      <PendingVarsNotice pending={false} onApply={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('offers to apply a staged change', () => {
    const onApply = vi.fn()
    render(<PendingVarsNotice pending onApply={onApply} />)

    expect(screen.getByText(/not running yet/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))
    expect(onApply).toHaveBeenCalledTimes(1)
  })

  it('disables the action while applying', () => {
    const onApply = vi.fn()
    render(<PendingVarsNotice pending onApply={onApply} applying />)

    const button = screen.getByRole('button', { name: /applying/i })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(onApply).not.toHaveBeenCalled()
  })
})
