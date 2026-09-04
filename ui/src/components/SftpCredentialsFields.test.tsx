import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { SftpCredentialsFields } from './SftpCredentialsFields'
import type { SftpCredentials } from '../api/types'

const creds: SftpCredentials = {
  host: 'dev.freepod.eu',
  port: 23,
  username: '7214d804-7f9b-46d2-b1f4-1b911b8a339e',
  auth_method: 'publickey',
  account_has_ssh_key: true,
}

function renderFields(overrides: Partial<SftpCredentials> = {}) {
  return render(
    <MemoryRouter>
      <SftpCredentialsFields creds={{ ...creds, ...overrides }} />
    </MemoryRouter>,
  )
}

describe('SftpCredentialsFields', () => {
  it('shows the connection details the API reported', () => {
    renderFields()
    expect(screen.getByText('dev.freepod.eu')).toBeInTheDocument()
    expect(screen.getByText('23')).toBeInTheDocument()
    expect(screen.getByText('7214d804-7f9b-46d2-b1f4-1b911b8a339e')).toBeInTheDocument()
  })

  it('shows no password field, masked or otherwise', () => {
    const { container } = renderFields()
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument()
    // A masked-but-empty field is the failure mode this replaces: bullets with
    // nothing behind them read as a value the page failed to load.
    expect(container.textContent).not.toMatch(/•/)
    expect(screen.queryByRole('button', { name: /show password/i })).not.toBeInTheDocument()
  })

  it('states that access uses a registered key, and links to where they live', () => {
    renderFields()
    expect(screen.getByText(/SSH key registered on your account/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /manage keys/i })).toHaveAttribute(
      'href',
      '/settings/ssh-keys',
    )
  })

  it('does not present the absent password as a failure or a pending value', () => {
    renderFields()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText(/unavailable|missing|failed|not available/i)).not.toBeInTheDocument()
  })

  describe('when the account has no registered key', () => {
    it('makes registering one the prominent instruction', () => {
      renderFields({ account_has_ssh_key: false })
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent(/register an ssh key before connecting/i)
      expect(screen.getByRole('link', { name: /add a key/i })).toHaveAttribute(
        'href',
        '/settings/ssh-keys',
      )
    })

    it('still shows the connection details, which are correct but unusable', () => {
      renderFields({ account_has_ssh_key: false })
      expect(screen.getByText('7214d804-7f9b-46d2-b1f4-1b911b8a339e')).toBeInTheDocument()
    })

    it('does not also claim the connection is key-authenticated as if ready', () => {
      renderFields({ account_has_ssh_key: false })
      expect(screen.queryByRole('link', { name: /manage keys/i })).not.toBeInTheDocument()
    })
  })
})
