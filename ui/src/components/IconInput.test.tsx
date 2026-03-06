import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { IconInput } from './IconInput'

class MockImage {
  naturalWidth = 100
  naturalHeight = 100
  onload: null | (() => void) = null
  onerror: null | (() => void) = null

  set src(_value: string) {
    setTimeout(() => this.onload?.(), 0)
  }
}

describe('IconInput', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('uses selected image automatically with no Apply button', async () => {
    vi.stubGlobal('Image', MockImage)
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:preview'),
      revokeObjectURL: vi.fn(),
    })

    const onChange = vi.fn()
    const { container } = render(<IconInput value={null} onChange={onChange} />)

    const input = container.querySelector('#icon-input') as HTMLInputElement
    const file = new File(['raw'], 'image.png', { type: 'image/png' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledTimes(1)
    })
    expect(onChange.mock.calls[0][0]).toBeInstanceOf(File)
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument()
  })

  it('scales oversized images down without cropping', async () => {
    class LargeImage extends MockImage {
      naturalWidth = 4000
      naturalHeight = 2000
    }

    vi.stubGlobal('Image', LargeImage)
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:preview'),
      revokeObjectURL: vi.fn(),
    })

    const drawImage = vi.fn()
    const canvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ({ drawImage })),
      toBlob: (cb: (blob: Blob | null) => void) => cb(new Blob(['scaled'], { type: 'image/png' })),
    }

    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName === 'canvas') {
        return canvas as unknown as HTMLCanvasElement
      }
      return originalCreateElement(tagName)
    })

    const onChange = vi.fn()
    const { container } = render(<IconInput value={null} onChange={onChange} />)

    const input = container.querySelector('#icon-input') as HTMLInputElement
    const file = new File(['raw'], 'huge.png', { type: 'image/png' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledTimes(1)
    })

    expect(canvas.width).toBe(2048)
    expect(canvas.height).toBe(1024)
    expect(drawImage).toHaveBeenCalledWith(expect.any(LargeImage), 0, 0, 2048, 1024)
  })
})
