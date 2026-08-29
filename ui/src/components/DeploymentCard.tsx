import { useEffect, useState } from 'react'
import {
  Alert,
  Avatar,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined'
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined'
import type { Deployment } from '../api/types'
import { resolveApiPath } from '../api/client'
import { isTransitionalStatus, statusColor } from '../utils/deploymentStatus'
import { ensureUrl, formatDateTime } from '../utils/format'
import { useSftpCredentials } from './SftpAccessPanel'
import { SftpAccessDialog } from './SftpAccessDialog'
import { useDatabaseDetails } from './DatabasePanel'
import { DatabaseAccessDialog } from './DatabaseAccessDialog'

interface DeploymentCardProps {
  deployment: Deployment
  userId: number
  deletePending: boolean
  onEdit: (deployment: Deployment) => void
  onDelete: (deployment: Deployment) => void
}

/**
 * A single deployment tile on the user dashboard: identity, status, and the
 * per-deployment actions (Open, Files, Edit, Delete). Extracted from Dashboard
 * so the page stays composition-only and per-deployment affordances have a home.
 */
export function DeploymentCard({
  deployment,
  userId,
  deletePending,
  onEdit,
  onDelete,
}: DeploymentCardProps) {
  const [sftpOpen, setSftpOpen] = useState(false)
  const [databaseOpen, setDatabaseOpen] = useState(false)

  // Doubles as the availability gate: the "Files" action only appears once the
  // credentials query resolves, so products that expose no files (404) show no
  // button, and opening the dialog is an instant cache hit.
  const { data: sftpCreds, refetch: refetchSftp } = useSftpCredentials(userId, deployment.id)
  const sftpAvailable = Boolean(sftpCreds)
  // Same gate, same reason: a deployment's database is provisioned before it
  // reaches ready, so an absent one on a settled deployment means the product
  // has none, and one absent on a transitional deployment is already described
  // by the deployment's own status.
  const { data: database, refetch: refetchDatabase } = useDatabaseDetails(userId, deployment.id)
  const databaseAvailable = Boolean(database)
  const settled = !isTransitionalStatus(deployment.status)
  useEffect(() => {
    if (settled && !sftpCreds) refetchSftp()
  }, [settled, sftpCreds, refetchSftp])
  useEffect(() => {
    if (settled && !database) refetchDatabase()
  }, [settled, database, refetchDatabase])

  const openable =
    deployment.hostname &&
    !(
      deployment.status === 'pending' ||
      deployment.status === 'deleting' ||
      (deployment.status === 'provisioning' && deployment.generation === 1)
    )

  return (
    <Card>
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={2} alignItems="flex-start">
            <Stack spacing={1} sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="h6" noWrap>{deployment.hostname}</Typography>
              <Typography variant="body2" color="text.secondary">
                {deployment.desired_template?.product?.name ?? 'Unknown product'}
                {deployment.subscription?.plan_template?.plan?.name
                  ? ` — ${deployment.subscription.plan_template.plan.name}`
                  : ''}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Created {formatDateTime(deployment.created_at)}
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Chip
                  size="small"
                  label={deployment.status === 'pending' ? 'Waiting for payment' : `Status: ${deployment.status ?? 'unknown'}`}
                  color={statusColor(deployment.status)}
                  icon={deployment.status === 'pending' ? <HourglassEmptyIcon /> : undefined}
                  variant="outlined"
                />
                {deployment.subscription?.payment_status === 'arrears' && deployment.status !== 'pending' && (
                  <Tooltip title="A recent payment has failed. Please update your payment method.">
                    <Chip
                      size="small"
                      label="Payment issue"
                      color="warning"
                      icon={<WarningAmberIcon />}
                      variant="outlined"
                    />
                  </Tooltip>
                )}
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Last reconcile {formatDateTime(deployment.last_reconcile_at)}
              </Typography>
            </Stack>
            <Avatar
              src={deployment.desired_template?.product?.icon_url ? resolveApiPath(deployment.desired_template.product.icon_url) : undefined}
              alt={deployment.desired_template?.product?.name}
              variant="rounded"
              sx={{ width: 64, height: 64, flexShrink: 0 }}
            >
              {deployment.desired_template?.product?.name?.[0] ?? '?'}
            </Avatar>
          </Stack>
          {deployment.last_error && (
            <Alert severity="error" sx={{ mt: 0.5 }}>
              {deployment.last_error}
            </Alert>
          )}
        </Stack>
      </CardContent>
      {isTransitionalStatus(deployment.status) && deployment.status !== 'pending' && (
        <LinearProgress
          color={deployment.status === 'deleting' ? 'secondary' : 'primary'}
          sx={{ mx: 2, borderRadius: 1 }}
        />
      )}
      <CardActions sx={{ px: 2, pb: 2 }}>
        {openable ? (
          <Button
            href={ensureUrl(deployment.hostname!)}
            target="_blank"
            rel="noreferrer"
            variant="contained"
          >
            Open
          </Button>
        ) : (
          <Button variant="contained" disabled>
            Open
          </Button>
        )}
        {sftpAvailable && (
          <Button
            variant="outlined"
            startIcon={<FolderOutlinedIcon />}
            onClick={() => setSftpOpen(true)}
          >
            Files
          </Button>
        )}
        {databaseAvailable && (
          <Button
            variant="outlined"
            startIcon={<StorageOutlinedIcon />}
            onClick={() => setDatabaseOpen(true)}
          >
            Database
          </Button>
        )}
        {deployment.status === 'ready' && (
          <Button variant="outlined" onClick={() => onEdit(deployment)}>
            Edit
          </Button>
        )}
        {deployment.status !== 'deleting' && deployment.status !== 'deleted' && (
          <Button
            variant="outlined"
            color="secondary"
            disabled={deletePending}
            onClick={() => onDelete(deployment)}
          >
            {deletePending ? 'Deleting...' : 'Delete'}
          </Button>
        )}
      </CardActions>

      {sftpOpen && (
        <SftpAccessDialog
          userId={userId}
          deploymentId={deployment.id}
          hostname={deployment.hostname}
          onClose={() => setSftpOpen(false)}
        />
      )}

      {databaseOpen && (
        <DatabaseAccessDialog
          userId={userId}
          deploymentId={deployment.id}
          hostname={deployment.hostname}
          onClose={() => setDatabaseOpen(false)}
        />
      )}
    </Card>
  )
}
