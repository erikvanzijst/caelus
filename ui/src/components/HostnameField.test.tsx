import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HostnameField } from './HostnameField'

const checkHostnameMock = vi.fn()

vi.mock('../api/endpoints', () => ({
  checkHostname: (...args: unknown[]) => checkHostnameMock(...args),
}))

describe('HostnameField', () => {
  describe('mode selection', () => {
    it('defaults to custom mode when no wildcard domains', () => {
      const onChange = vi.fn()
      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      expect(screen.getByLabelText('Hostname')).toBeInTheDocument()
      expect(screen.queryByText('Caelus domain')).not.toBeInTheDocument()
    })

    it('defaults to wildcard mode when wildcard domains are provided', () => {
      const onChange = vi.fn()
      render(
        <HostnameField value="" onChange={onChange} wildcardDomains={['app.example.com']} />,
      )

      expect(screen.getByLabelText('Hostname')).toBeInTheDocument()
      expect(screen.getByText('app.example.com')).toBeInTheDocument()
      expect(screen.getByText('Caelus domain')).toBeInTheDocument()
      expect(screen.getByText('Custom domain')).toBeInTheDocument()
    })

    it('switches from wildcard to custom mode', () => {
      const onChange = vi.fn()
      render(
        <HostnameField value="" onChange={onChange} wildcardDomains={['app.example.com']} />,
      )

      fireEvent.click(screen.getByText('Custom domain'))
      expect(screen.getByLabelText('Hostname')).toBeInTheDocument()
    })

    it('switches from custom back to wildcard mode', () => {
      const onChange = vi.fn()
      render(
        <HostnameField value="" onChange={onChange} wildcardDomains={['app.example.com']} />,
      )

      fireEvent.click(screen.getByText('Custom domain'))
      fireEvent.click(screen.getByText('Caelus domain'))
      expect(screen.getByText('app.example.com')).toBeInTheDocument()
    })
  })

  describe('value composition', () => {
    it('combines prefix and domain in wildcard mode', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'myapp.app.example.com', usable: true, reason: null })

      render(
        <HostnameField value="" onChange={onChange} wildcardDomains={['app.example.com']} />,
      )

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'myapp' } })

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith('myapp.app.example.com')
      })
    })

    it('uses full value in custom mode', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'myapp.custom.com', usable: true, reason: null })

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'myapp.custom.com' } })

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith('myapp.custom.com')
      })
    })

    it('does not call onChange for empty prefix in wildcard mode', () => {
      const onChange = vi.fn()
      render(
        <HostnameField value="" onChange={onChange} wildcardDomains={['app.example.com']} />,
      )

      expect(onChange).not.toHaveBeenCalled()
    })
  })

  describe('debounced validation', () => {
    it('calls checkHostname after debounce', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'test.example.com', usable: true, reason: null })

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'test.example.com' } })

      // Synchronously after typing: API should not yet be called (debounce pending)
      expect(checkHostnameMock).not.toHaveBeenCalled()

      // After the debounce fires
      await waitFor(() => {
        expect(checkHostnameMock).toHaveBeenCalledWith('test.example.com')
      })
    })

    it('does not call API when input is empty', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockClear()

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      // Type something then clear it
      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'x' } })
      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: '' } })

      // Wait longer than the debounce
      await new Promise((r) => setTimeout(r, 500))
      expect(checkHostnameMock).not.toHaveBeenCalled()
    })

    it('shows success icon when hostname is usable', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'good.example.com', usable: true, reason: null })

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'good.example.com' } })

      await waitFor(() => {
        expect(screen.getByTestId('CheckCircleIcon')).toBeInTheDocument()
      })
    })

    it('shows error icon and helper text for invalid hostname', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'bad', usable: false, reason: 'invalid' })

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'bad' } })

      await waitFor(() => {
        expect(screen.getByTestId('ErrorIcon')).toBeInTheDocument()
        expect(screen.getByText('Invalid hostname format')).toBeInTheDocument()
      })
    })

    it('shows in-use error message', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'taken.example.com', usable: false, reason: 'in_use' })

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'taken.example.com' } })

      await waitFor(() => {
        expect(screen.getByText('Already in use')).toBeInTheDocument()
      })
    })

    it('shows reserved error message', async () => {
      const onChange = vi.fn()
      checkHostnameMock.mockResolvedValue({ fqdn: 'smtp.example.com', usable: false, reason: 'reserved' })

      render(<HostnameField value="" onChange={onChange} wildcardDomains={[]} />)

      fireEvent.change(screen.getByLabelText('Hostname'), { target: { value: 'smtp.example.com' } })

      await waitFor(() => {
        expect(screen.getByText('Hostname is reserved')).toBeInTheDocument()
      })
    })
  })

  describe('async domain loading', () => {
    it('switches to wildcard mode when domains arrive after mount', () => {
      const onChange = vi.fn()
      const { rerender } = render(
        <HostnameField value="" onChange={onChange} wildcardDomains={[]} />,
      )

      // Initially in custom mode (no domains yet)
      expect(screen.getByLabelText('Hostname')).toBeInTheDocument()
      expect(screen.queryByText('Caelus domain')).not.toBeInTheDocument()

      // Domains arrive asynchronously
      rerender(
        <HostnameField value="" onChange={onChange} wildcardDomains={['app.example.com']} />,
      )

      // Should switch to wildcard mode with domain pre-selected
      expect(screen.getByText('Caelus domain')).toBeInTheDocument()
      expect(screen.getByText('app.example.com')).toBeInTheDocument()
    })
  })

  describe('initial value sync', () => {
    it('splits initial value into prefix and domain in wildcard mode', () => {
      const onChange = vi.fn()
      render(
        <HostnameField
          value="myapp.app.example.com"
          onChange={onChange}
          wildcardDomains={['app.example.com']}
        />,
      )

      expect(screen.getByLabelText('Hostname')).toHaveValue('myapp')
    })

    it('falls back to custom mode when value does not match any wildcard domain', () => {
      const onChange = vi.fn()
      render(
        <HostnameField
          value="myapp.other.com"
          onChange={onChange}
          wildcardDomains={['app.example.com']}
        />,
      )

      expect(screen.getByLabelText('Hostname')).toHaveValue('myapp.other.com')
    })
  })

  describe('external error prop', () => {
    it('displays external error message', () => {
      const onChange = vi.fn()
      render(
        <HostnameField
          value=""
          onChange={onChange}
          wildcardDomains={[]}
          error="Server rejected hostname"
        />,
      )

      expect(screen.getByText('Server rejected hostname')).toBeInTheDocument()
    })
  })
})
