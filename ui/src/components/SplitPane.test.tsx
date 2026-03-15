import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SplitPane } from './SplitPane'

describe('SplitPane', () => {
  it('renders both left and right content', () => {
    render(
      <SplitPane
        left={<div>Left content</div>}
        right={<div>Right content</div>}
      />,
    )

    expect(screen.getByText('Left content')).toBeInTheDocument()
    expect(screen.getByText('Right content')).toBeInTheDocument()
  })

  it('renders the draggable divider', () => {
    const { container } = render(
      <SplitPane
        left={<div>Left</div>}
        right={<div>Right</div>}
      />,
    )

    const divider = container.querySelector('[style*="cursor"]') ||
      container.querySelector('[class*="MuiBox-root"]:nth-child(2)')
    expect(divider).toBeInTheDocument()
  })

  it('sets initial left pane width from defaultLeftPercent', () => {
    const { container } = render(
      <SplitPane
        left={<div>Left</div>}
        right={<div>Right</div>}
        defaultLeftPercent={30}
      />,
    )

    const leftPane = container.querySelector('[class*="MuiBox-root"] > [class*="MuiBox-root"]')
    expect(leftPane).toHaveStyle({ width: '30%' })
  })

  it('handles mousedown on divider without error', () => {
    const { container } = render(
      <SplitPane
        left={<div>Left</div>}
        right={<div>Right</div>}
      />,
    )

    // The divider is the second child of the flex container
    const flexContainer = container.firstElementChild!
    const divider = flexContainer.children[1]
    expect(divider).toBeInTheDocument()

    // Should not throw
    fireEvent.mouseDown(divider, { clientX: 400 })
    fireEvent.mouseMove(document, { clientX: 300 })
    fireEvent.mouseUp(document)
  })
})
