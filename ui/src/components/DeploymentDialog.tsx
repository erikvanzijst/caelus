import { useEffect } from 'react'
import { Box, Button, Dialog, DialogActions, DialogContent, Divider, LinearProgress, Typography } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Deployment } from '../api/types'
import { getDeployment, updateDeployment } from '../api/endpoints'
import { isTransitionalStatus } from '../utils/deploymentStatus'
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

export function DeploymentDialog({ deployment: initialDeployment, onClose }: DeploymentDialogProps) {
  const queryClient = useQueryClient()

  // Poll the single deployment while the dialog is open
  const { data: polledDeployment } = useQuery({
    queryKey: ['deployment', initialDeployment?.user_id, initialDeployment?.id],
    queryFn: () => getDeployment(initialDeployment!.user_id, initialDeployment!.id),
    enabled: Boolean(initialDeployment),
    initialData: initialDeployment ?? undefined,
    refetchInterval: (query) => {
      const d = query.state.data
      return d && isTransitionalStatus(d.status) ? 1000 : false
    },
  })

  // Patch the admin-deployments list cache whenever the polled deployment changes
  useEffect(() => {
    if (!polledDeployment) return
    queryClient.setQueryData<Deployment[]>(['admin-deployments'], (old) =>
      old?.map((d) => d.id === polledDeployment.id ? polledDeployment : d),
    )
  }, [polledDeployment, queryClient])

  const deployment = polledDeployment ?? initialDeployment

  const template = deployment?.applied_template ?? deployment?.desired_template
  const product = template?.product
  const appliedId = deployment?.applied_template?.id
  const canonicalId = deployment?.applied_template?.product?.template_id
  const isUpToDate = appliedId != null && canonicalId != null && appliedId === canonicalId
  const isTransitioning = isTransitionalStatus(deployment?.status)

  const upgradeMutation = useMutation({
    mutationFn: () =>
      updateDeployment(deployment!.user_id, deployment!.id, {
        desired_template_id: canonicalId!,
        user_values_json: deployment!.user_values_json ?? undefined,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['deployment', updated.user_id, updated.id], updated)
      queryClient.setQueryData<Deployment[]>(['admin-deployments'], (old) =>
        old?.map((d) => d.id === updated.id ? updated : d),
      )
    },
  })

  if (!deployment) return null

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
        {isTransitioning && (
          <LinearProgress sx={{ my: 2, borderRadius: 1 }} />
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
        <Button
          variant="contained"
          color="primary"
          disabled={isUpToDate || isTransitioning || upgradeMutation.isPending}
          onClick={() => upgradeMutation.mutate()}
        >
          {upgradeMutation.isPending || isTransitioning
            ? 'Upgrading...'
            : isUpToDate
              ? 'Up to date'
              : `Upgrade to #${canonicalId}`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
