import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { UserValuesForm } from '../components/UserValuesForm'

describe('UserValuesForm', () => {
  const schema = {
    type: 'object',
    properties: {
      ingress: {
        type: 'object',
        properties: {
          host: {
            type: 'string',
            title: 'Domain name',
            minLength: 1,
            maxLength: 64,
          },
        },
        required: ['host'],
      },
      user: {
        type: 'object',
        properties: {
          message: {
            type: 'string',
            title: 'Message',
            maxLength: 2000,
          },
        },
      },
    },
    required: ['ingress'],
  }

  const defaults = {
    ingress: {
      host: 'default.example.com',
    },
    user: {
      message: 'Hello World',
    },
  }

  it('renders form when schema is provided', () => {
    const onChange = vi.fn()
    render(
      <UserValuesForm
        valuesSchemaJson={schema}
        defaultValuesJson={null}
        onChange={onChange}
      />,
    )

    expect(screen.getByText('Configure application values')).toBeInTheDocument()
    expect(screen.getAllByText('Domain name').length).toBeGreaterThan(0)
  })

  it('prefills form with default values', async () => {
    const onChange = vi.fn()
    render(
      <UserValuesForm
        valuesSchemaJson={schema}
        defaultValuesJson={defaults}
        onChange={onChange}
      />,
    )

    await waitFor(() => {
      const inputs = document.querySelectorAll('input')
      const hostInput = Array.from(inputs).find((input) => input.value === 'default.example.com')
      expect(hostInput).toBeInTheDocument()
    })
  })

  it('calls onChange with defaults when loaded', async () => {
    const onChange = vi.fn()
    render(
      <UserValuesForm
        valuesSchemaJson={schema}
        defaultValuesJson={defaults}
        onChange={onChange}
      />,
    )

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith({
        ingress: { host: 'default.example.com' },
        user: { message: 'Hello World' },
      })
    })
  })

  it('returns null when schema is null', () => {
    const onChange = vi.fn()
    const { container } = render(
      <UserValuesForm
        valuesSchemaJson={null}
        defaultValuesJson={null}
        onChange={onChange}
      />,
    )

    expect(container.firstChild).toBeNull()
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('returns null when schema has no properties', () => {
    const onChange = vi.fn()
    const { container } = render(
      <UserValuesForm
        valuesSchemaJson={{ type: 'object', properties: {} }}
        defaultValuesJson={null}
        onChange={onChange}
      />,
    )

    expect(container.firstChild).toBeNull()
  })
})
