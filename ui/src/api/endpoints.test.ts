import { describe, expect, it, vi } from 'vitest'
import { createDeployment, createTemplate } from './endpoints'
import { requestJson } from './client'

vi.mock('./client', () => ({
  requestJson: vi.fn(),
}))

describe('endpoints payload contracts', () => {
  it('creates templates with chart_ref/chart_version payload', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    await createTemplate(4, { chart_ref: 'ghcr.io/org/chart', chart_version: '1.2.3' }, 'a@b.com')

    expect(requestJson).toHaveBeenCalledWith('/products/4/templates', {
      method: 'POST',
      body: JSON.stringify({
        chart_ref: 'ghcr.io/org/chart',
        chart_version: '1.2.3',
      }),
      authEmail: 'a@b.com',
    })
  })

  it('creates deployments with desired_template_id payload', async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({} as never)

    await createDeployment(
      3,
      { desired_template_id: 7, domainname: 'app.example.com' },
      'a@b.com',
    )

    expect(requestJson).toHaveBeenCalledWith('/users/3/deployments', {
      method: 'POST',
      body: JSON.stringify({
        desired_template_id: 7,
        domainname: 'app.example.com',
      }),
      authEmail: 'a@b.com',
    })
  })
})
