import type { DeploymentStatus } from '../api/types'

export function statusColor(
  status?: DeploymentStatus,
): 'default' | 'info' | 'warning' | 'success' | 'error' {
  switch (status) {
    case 'ready':
      return 'success'
    case 'error':
      return 'error'
    case 'provisioning':
    case 'deleting':
      return 'warning'
    case 'deleted':
      return 'default'
    default:
      return 'info'
  }
}

export function isTransitionalStatus(status?: DeploymentStatus) {
  return status === 'provisioning' || status === 'deleting'
}
