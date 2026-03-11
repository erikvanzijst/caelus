import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { NewProduct } from './NewProduct'

const createProductMock = vi.fn()

vi.mock('../api/endpoints', () => ({
  createProduct: (...args: unknown[]) => createProductMock(...args),
}))

vi.mock('./IconInput', () => ({
  IconInput: ({ value, onChange }: { value: File | null; onChange: (file: File | null) => void }) => (
    <div>
      <button onClick={() => onChange(new File(['x'], 'icon.png', { type: 'image/png' }))}>Pick icon</button>
      <div data-testid="icon-state">{value ? 'selected' : 'empty'}</div>
    </div>
  ),
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

describe('NewProduct', () => {
  it('clears name, description, and icon after successful submit', async () => {
    createProductMock.mockResolvedValue({ id: 1, name: 'demo' })

    const onSuccess = vi.fn()
    const onError = vi.fn()

    renderWithQuery(
      <NewProduct onSuccess={onSuccess} onError={onError} />,
    )

    fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'My Product' } })
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'My Description' } })
    fireEvent.click(screen.getByRole('button', { name: 'Pick icon' }))

    expect(screen.getByTestId('icon-state')).toHaveTextContent('selected')

    fireEvent.click(screen.getByRole('button', { name: 'Add product' }))

    await waitFor(() => {
      expect(createProductMock).toHaveBeenCalledWith(
        { name: 'My Product', description: 'My Description' },
        expect.any(File),
      )
    })

    await waitFor(() => {
      expect(screen.getByLabelText('Product name')).toHaveValue('')
      expect(screen.getByLabelText('Description')).toHaveValue('')
      expect(screen.getByTestId('icon-state')).toHaveTextContent('empty')
      expect(onSuccess).toHaveBeenCalled()
    })
  })
})
