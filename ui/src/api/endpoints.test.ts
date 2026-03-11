import { describe, expect, it, vi } from 'vitest'
import { createDeployment, createTemplate } from './endpoints'
import { requestJson } from './client'

vi.mock('./client', () => ({
  requestJson: vi.fn(),
}))

describe('endpoints payload contracts', () => {
  it('creates templates with values_schema_json payload', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    const schema = {
      type: 'object',
      properties: {
        message: { type: 'string' },
      },
    }

    await createTemplate(
      4,
      { chart_ref: 'ghcr.io/org/chart', chart_version: '1.2.3', values_schema_json: schema },
    )

    expect(requestJson).toHaveBeenCalledWith('/products/4/templates', {
      method: 'POST',
      body: JSON.stringify({
        chart_ref: 'ghcr.io/org/chart',
        chart_version: '1.2.3',
        values_schema_json: schema,
      }),
    })
  })

  it('creates templates with default_values_json payload', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    const defaults = {
      user: {
        message: 'Hello World!',
      },
    }

    await createTemplate(
      4,
      { chart_ref: 'ghcr.io/org/chart', chart_version: '1.2.3', default_values_json: defaults },
    )

    expect(requestJson).toHaveBeenCalledWith('/products/4/templates', {
      method: 'POST',
      body: JSON.stringify({
        chart_ref: 'ghcr.io/org/chart',
        chart_version: '1.2.3',
        default_values_json: defaults,
      }),
    })
  })

  it('creates deployments with desired_template_id payload', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    await createDeployment(3, { desired_template_id: 7 })

    expect(requestJson).toHaveBeenCalledWith('/users/3/deployments', {
      method: 'POST',
      body: JSON.stringify({
        desired_template_id: 7,
      }),
    })
  })

  it('creates deployments with user_values_json payload without domainname value', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    const userValues = {
      user: { message: 'Hello' },
    }

    await createDeployment(
      3,
      { desired_template_id: 7, user_values_json: userValues },
    )

    expect(requestJson).toHaveBeenCalledWith('/users/3/deployments', {
      method: 'POST',
      body: JSON.stringify({
        desired_template_id: 7,
        user_values_json: userValues,
      }),
    })
  })

  it('creates deployments with user_values_json payload with domainname value', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    const userValues = {
      ingress: { host: 'example.com', domainname: 'example.com' },
      user: { message: 'Hello' },
    }

    await createDeployment(3, { desired_template_id: 7, user_values_json: userValues })

    expect(requestJson).toHaveBeenCalledWith('/users/3/deployments', {
      method: 'POST',
      body: JSON.stringify({
        desired_template_id: 7,
        user_values_json: userValues,
      }),
    })
  })
})
