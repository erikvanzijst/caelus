import { Box, Button, Dialog, DialogActions, DialogContent, Divider, Typography } from '@mui/material'
import type { Deployment } from '../api/types'
import { DeployDialogContent } from './DeployDialogContent'

interface DeploymentDialogProps {
  deployment: Deployment | null
  onClose: () => void
}

function formatIso(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toISOString().replace('T', ' ').slice(0, 19)
}

function formatAge(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.now() - new Date(value).getTime()
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) return `${days}d ${hours % 24}h`
  if (hours > 0) return `${hours}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m`
  return 'just now'
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'flex', gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 160 }}>
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  )
}

export function DeploymentDialog({ deployment, onClose }: DeploymentDialogProps) {
  if (!deployment) return null

  const template = deployment.applied_template ?? deployment.desired_template
  const product = template?.product
  const appliedId = deployment.applied_template?.id
  const canonicalId = deployment.applied_template?.product?.template_id
  const isUpToDate = appliedId != null && canonicalId != null && appliedId === canonicalId

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent>
        {product && template && (
          <DeployDialogContent
            product={product}
            valuesSchemaJson={template.values_schema_json ?? null}
            initialValuesJson={deployment.user_values_json ?? null}
            onChange={() => {}}
            initialHostname={deployment.hostname ?? undefined}
            readOnly
          />
        )}
        <Divider sx={{ my: 2 }} />
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <MetadataRow label="Owner" value={deployment.user?.email ?? '—'} />
          <MetadataRow label="Created" value={formatIso(deployment.created_at)} />
          <MetadataRow label="Age" value={formatAge(deployment.created_at)} />
          <MetadataRow label="Last reconciliation" value={formatIso(deployment.last_reconcile_at)} />
          <MetadataRow label="Current template" value={deployment.applied_template ? `#${deployment.applied_template.id}` : '—'} />
          <MetadataRow label="Status" value={deployment.status ?? '—'} />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color="primary" disabled={isUpToDate}>
          {isUpToDate ? 'Up to date' : `Upgrade to #${canonicalId}`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
