import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { SshKeysPanel } from './SshKeysPanel'
import { ApiError } from '../api/client'
import type { SshKey } from '../api/types'

const listSshKeysMock = vi.fn()
const addSshKeyMock = vi.fn()
const deleteSshKeyMock = vi.fn()

vi.mock('../api/endpoints', () => ({
  listSshKeys: (...args: unknown[]) => listSshKeysMock(...args),
  addSshKey: (...args: unknown[]) => addSshKeyMock(...args),
  deleteSshKey: (...args: unknown[]) => deleteSshKeyMock(...args),
}))

vi.mock('../state/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 7, email: 'dev@example.com', is_admin: false, created_at: '2026-01-01T00:00:00Z' },
    loading: false,
    email: 'dev@example.com',
    setEmail: vi.fn(),
  }),
}))

const KEY_LINE = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPd9QinZvJYT'

/** A File whose `text()` resolves, which jsdom does not always provide. */
function makeFile(name: string, body: string): File {
  const file = new File([body], name, { type: 'text/plain' })
  Object.defineProperty(file, 'text', { value: () => Promise.resolve(body) })
  Object.defineProperty(file, 'size', { value: body.length })
  return file
}

const key: SshKey = {
  fingerprint: 'SHA256:aRFKFZTmjMSb54b9QvQXMr8wbTm5L87RZKMD/fZsYkA',
  key_type: 'ssh-ed25519',
  bits: 256,
  label: 'erik@thinkpad',
  public_key: KEY_LINE,
  created_at: '2026-08-27T10:12:03Z',
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SshKeysPanel />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listSshKeysMock.mockReset()
  addSshKeyMock.mockReset()
  deleteSshKeyMock.mockReset()
})

async function openAddDialog() {
  fireEvent.click(await screen.findByRole('button', { name: /add ssh key|add key/i }))
  return screen.findByLabelText(/public key/i)
}

describe('SshKeysPanel', () => {
  it('lists a key with its label, fingerprint, type and date', async () => {
    listSshKeysMock.mockResolvedValue([key])
    renderPanel()

    expect(await screen.findByText('erik@thinkpad')).toBeInTheDocument()
    expect(screen.getByText(key.fingerprint)).toBeInTheDocument()
    expect(screen.getByText('Ed25519')).toBeInTheDocument()
    expect(screen.getByText(/Added/)).toBeInTheDocument()
  })

  it('explains itself when the account holds no keys', async () => {
    listSshKeysMock.mockResolvedValue([])
    renderPanel()

    expect(await screen.findByText(/No SSH keys yet/i)).toBeInTheDocument()
    expect(screen.getByText(/freepod key add/)).toBeInTheDocument()
  })

  it('names an unlabeled key by its fingerprint, not a placeholder', async () => {
    listSshKeysMock.mockResolvedValue([{ ...key, label: null }])
    const { container } = renderPanel()

    // The fingerprint carries the identity, and appears once rather than twice.
    const shown = await screen.findAllByText(key.fingerprint)
    expect(shown).toHaveLength(1)
    expect(container.textContent).not.toMatch(/unlabel|no label|untitled/i)
    expect(
      screen.getByRole('button', { name: `Remove ${key.fingerprint}` }),
    ).toBeInTheDocument()
  })

  it('confirms deletion of an unlabeled key by fingerprint', async () => {
    listSshKeysMock.mockResolvedValue([{ ...key, label: null }])
    deleteSshKeyMock.mockResolvedValue(null)
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: `Remove ${key.fingerprint}` }))
    expect(screen.getByText(/permanently delete/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(deleteSshKeyMock).toHaveBeenCalledWith(7, key.fingerprint),
    )
  })

  it('adds a pasted key', async () => {
    listSshKeysMock.mockResolvedValue([])
    addSshKeyMock.mockResolvedValue(key)
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.click(screen.getByRole('button', { name: 'Add key' }))

    await waitFor(() =>
      expect(addSshKeyMock).toHaveBeenCalledWith(7, { public_key: KEY_LINE }),
    )
  })

  it('opens empty again after a successful add', async () => {
    // The panel closes the dialog itself on success, without going through
    // any cancel path, and this component stays mounted throughout.
    listSshKeysMock.mockResolvedValue([])
    addSshKeyMock.mockResolvedValue(key)
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.change(screen.getByLabelText(/label/i), { target: { value: 'Work laptop' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add key' }))

    await waitFor(() => expect(addSshKeyMock).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByLabelText(/public key/i)).toBeNull())

    const reopened = await openAddDialog()
    expect((reopened as HTMLTextAreaElement).value).toBe('')
    expect((screen.getByLabelText(/label/i) as HTMLInputElement).value).toBe('')
  })

  it('opens empty again after cancelling', async () => {
    listSshKeysMock.mockResolvedValue([])
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByLabelText(/public key/i)).toBeNull())

    const reopened = await openAddDialog()
    expect((reopened as HTMLTextAreaElement).value).toBe('')
  })

  it('clears a previous rejection when reopened', async () => {
    listSshKeysMock.mockResolvedValue([])
    addSshKeyMock.mockRejectedValue(new ApiError('nope', 409, 'duplicate_key'))
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.click(screen.getByRole('button', { name: 'Add key' }))
    expect(await screen.findByText(/already registered/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByLabelText(/public key/i)).toBeNull())

    await openAddDialog()
    expect(screen.queryByText(/already registered/i)).toBeNull()
  })

  it('sends a supplied label alongside the key', async () => {
    listSshKeysMock.mockResolvedValue([])
    addSshKeyMock.mockResolvedValue(key)
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.change(screen.getByLabelText(/label/i), { target: { value: 'Work laptop' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add key' }))

    await waitFor(() =>
      expect(addSshKeyMock).toHaveBeenCalledWith(7, {
        public_key: KEY_LINE,
        label: 'Work laptop',
      }),
    )
  })

  it('refuses private key material without submitting it', async () => {
    listSshKeysMock.mockResolvedValue([])
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, {
      target: { value: '-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----' },
    })

    expect(screen.getByText(/must never leave your machine/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add key' })).toBeDisabled()
    expect(addSshKeyMock).not.toHaveBeenCalled()
  })

  it.each([
    ['duplicate_key', 409, /already registered/i],
    ['key_too_short', 400, /too short/i],
    ['unsupported_key_type', 400, /not supported/i],
    ['multiple_keys', 400, /one at a time/i],
    ['private_key_material', 400, /private key/i],
  ])('reads %s distinctly', async (code, status, expected) => {
    listSshKeysMock.mockResolvedValue([])
    addSshKeyMock.mockRejectedValue(new ApiError('platform prose', status, code))
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.click(screen.getByRole('button', { name: 'Add key' }))

    expect(await screen.findByText(expected)).toBeInTheDocument()
  })

  it('falls back to the platform message for an unrecognised code', async () => {
    listSshKeysMock.mockResolvedValue([])
    addSshKeyMock.mockRejectedValue(new ApiError('something new went wrong', 400, 'brand_new_code'))
    renderPanel()

    const field = await openAddDialog()
    fireEvent.change(field, { target: { value: KEY_LINE } })
    fireEvent.click(screen.getByRole('button', { name: 'Add key' }))

    expect(await screen.findByText('something new went wrong')).toBeInTheDocument()
  })

  it('confirms a deletion, naming the key and its consequence', async () => {
    listSshKeysMock.mockResolvedValue([key])
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Remove erik@thinkpad' }))

    expect(screen.getByText(/permanently delete/i)).toBeInTheDocument()
    expect(screen.getByText(/will lose access/i)).toBeInTheDocument()
    expect(deleteSshKeyMock).not.toHaveBeenCalled()
  })

  it('deletes by fingerprint once confirmed', async () => {
    listSshKeysMock.mockResolvedValue([key])
    deleteSshKeyMock.mockResolvedValue(null)
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Remove erik@thinkpad' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(deleteSshKeyMock).toHaveBeenCalledWith(7, key.fingerprint),
    )
  })

  it('keeps the key when the confirmation is cancelled', async () => {
    listSshKeysMock.mockResolvedValue([key])
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Remove erik@thinkpad' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByText(/permanently delete/i)).toBeNull())
    expect(deleteSshKeyMock).not.toHaveBeenCalled()
  })

  it('never renders private key material', async () => {
    listSshKeysMock.mockResolvedValue([key])
    const { container } = renderPanel()

    await screen.findByText('erik@thinkpad')
    expect(container.textContent).not.toMatch(/PRIVATE KEY/i)
  })

  it('loads a dropped .pub file into the field', async () => {
    listSshKeysMock.mockResolvedValue([])
    renderPanel()
    await openAddDialog()

    const dropTarget = document.querySelector('.MuiDialogContent-root')!
    fireEvent.drop(dropTarget, {
      dataTransfer: { files: [makeFile('id_ed25519.pub', `${KEY_LINE} me@laptop\n`)] },
    })

    await waitFor(() =>
      expect((screen.getByLabelText(/public key/i) as HTMLTextAreaElement).value).toBe(
        `${KEY_LINE} me@laptop`,
      ),
    )
  })

  it('refuses a dropped private key without ever putting it in the field', async () => {
    listSshKeysMock.mockResolvedValue([])
    const { container } = renderPanel()
    await openAddDialog()

    const secret = 'SECRETKEYBODY'
    const dropTarget = document.querySelector('.MuiDialogContent-root')!
    fireEvent.drop(dropTarget, {
      dataTransfer: {
        files: [
          makeFile(
            'id_ed25519',
            `-----BEGIN OPENSSH PRIVATE KEY-----\n${secret}\n-----END OPENSSH PRIVATE KEY-----`,
          ),
        ],
      },
    })

    expect(await screen.findByText(/is a private key/i)).toBeInTheDocument()
    expect(screen.getByText(/id_ed25519\.pub instead/)).toBeInTheDocument()
    expect((screen.getByLabelText(/public key/i) as HTMLTextAreaElement).value).toBe('')
    expect(container.innerHTML).not.toContain(secret)
    expect(document.body.innerHTML).not.toContain(secret)
  })

  it('refuses a file too large to be a public key', async () => {
    listSshKeysMock.mockResolvedValue([])
    renderPanel()
    await openAddDialog()

    const dropTarget = document.querySelector('.MuiDialogContent-root')!
    fireEvent.drop(dropTarget, {
      dataTransfer: { files: [makeFile('huge.pub', 'x'.repeat(64 * 1024 + 1))] },
    })

    expect(await screen.findByText(/too large to be a public key/i)).toBeInTheDocument()
  })

  it('points at the client rather than generating a key in the browser', async () => {
    listSshKeysMock.mockResolvedValue([])
    renderPanel()

    await openAddDialog()
    expect(screen.getByText(/never generated in the browser/i)).toBeInTheDocument()
  })
})
