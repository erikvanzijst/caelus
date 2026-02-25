import { describe, expect, it } from 'vitest'
import { isTransitionalStatus, statusColor } from './deploymentStatus'

describe('deployment status helpers', () => {
  it('maps known statuses to UI colors', () => {
    expect(statusColor('provisioning')).toBe('warning')
    expect(statusColor('ready')).toBe('success')
    expect(statusColor('deleting')).toBe('warning')
    expect(statusColor('deleted')).toBe('default')
    expect(statusColor('error')).toBe('error')
  })

  it('treats only provisioning and deleting as transitional', () => {
    expect(isTransitionalStatus('provisioning')).toBe(true)
    expect(isTransitionalStatus('deleting')).toBe(true)
    expect(isTransitionalStatus('ready')).toBe(false)
    expect(isTransitionalStatus('deleted')).toBe(false)
    expect(isTransitionalStatus('error')).toBe(false)
  })
})
