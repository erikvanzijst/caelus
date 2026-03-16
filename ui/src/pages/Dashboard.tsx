import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  deleteDeployment,
  listDeployments,
  listProducts,
} from '../api/endpoints'
import type { Deployment, Product } from '../api/types'
import { resolveApiPath } from '../api/client'
import { useAuth } from '../state/AuthContext'
import { isTransitionalStatus, statusColor } from '../utils/deploymentStatus'
import { ensureUrl, formatDateTime } from '../utils/format'
import { ProductList } from '../components/ProductList'
import { DeployDialog } from '../components/DeployDialog'

function Dashboard() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [deletePendingIds, setDeletePendingIds] = useState<Set<number>>(new Set())
  const [deployProduct, setDeployProduct] = useState<Product | null>(null)
  const [editDeployment, setEditDeployment] = useState<Deployment | null>(null)

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
    enabled: Boolean(user),
  })

  const deployableProducts = useMemo<Product[]>(() => {
    return (productsQuery.data ?? []).filter((product) => Boolean(product.template_id))
  }, [productsQuery.data])

  const deploymentsQuery = useQuery({
    queryKey: ['deployments', user?.id],
    queryFn: () => listDeployments(user!.id),
    enabled: Boolean(user?.id),
    refetchInterval: (query) => {
      const items = query.state.data ?? []
      return items.some((deployment) => isTransitionalStatus(deployment.status)) ? 3000 : false
    },
  })

  const deleteDeploymentMutation = useMutation({
    mutationFn: (deploymentId: number) =>
      deleteDeployment(user!.id, deploymentId),
    onMutate: (deploymentId) => {
      setDeletePendingIds((previous) => new Set(previous).add(deploymentId))
      return { deploymentId }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deployments'] }),
    onError: (_error, deploymentId) => {
      setDeletePendingIds((previous) => {
        const next = new Set(previous)
        next.delete(deploymentId)
        return next
      })
    },
  })

  useEffect(() => {
    const visibleIds = new Set((deploymentsQuery.data ?? []).map((deployment) => deployment.id))
    setDeletePendingIds((previous) => {
      let changed = false
      const next = new Set<number>()
      previous.forEach((id) => {
        if (visibleIds.has(id)) {
          next.add(id)
        } else {
          changed = true
        }
      })
      return changed ? next : previous
    })
  }, [deploymentsQuery.data])

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h3">Your applications</Typography>
        <Typography color="text.secondary">
          Spin up new products and keep track of your live environments.
        </Typography>
      </Box>

      <Grid container spacing={2}>
        {deploymentsQuery.data
          ?.filter((deployment) => deployment.status !== 'deleted')
          .map((deployment) => (
          <Grid size={{ xs: 12, md: 6 }} key={deployment.id}>
            <Card>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={2} alignItems="flex-start">
                    <Stack spacing={1} sx={{ minWidth: 0, flex: 1 }}>
                      <Typography variant="h6" noWrap>{deployment.hostname}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {deployment.desired_template?.product?.name ?? 'Unknown product'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Created {formatDateTime(deployment.created_at)}
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                        <Chip
                          size="small"
                          label={`Status: ${deployment.status ?? 'unknown'}`}
                          color={statusColor(deployment.status)}
                          variant="outlined"
                        />
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
              {isTransitionalStatus(deployment.status) && (
                <LinearProgress
                  color={deployment.status === 'deleting' ? 'secondary' : 'primary'}
                  sx={{ mx: 2, borderRadius: 1 }}
                />
              )}
              <CardActions sx={{ px: 2, pb: 2 }}>
                {deployment.hostname && !(deployment.status === 'deleting' || (deployment.status === 'provisioning' && deployment.generation === 1)) ? (
                  <Button
                    href={ensureUrl(deployment.hostname)}
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
                {deployment.status === 'ready' && (
                  <Button
                    variant="outlined"
                    onClick={() => setEditDeployment(deployment)}
                  >
                    Edit
                  </Button>
                )}
                {deployment.status !== 'deleting' && deployment.status !== 'deleted' && (
                  <Button
                    variant="outlined"
                    color="secondary"
                    disabled={deletePendingIds.has(deployment.id)}
                    onClick={() => {
                      if (window.confirm('Delete this deployment?')) {
                        deleteDeploymentMutation.mutate(deployment.id)
                      }
                    }}
                  >
                    {deletePendingIds.has(deployment.id) ? 'Deleting...' : 'Delete'}
                  </Button>
                )}
              </CardActions>
            </Card>
          </Grid>
        ))}
        {!deploymentsQuery.isLoading &&
          (deploymentsQuery.data?.filter((deployment) => deployment.status !== 'deleted').length ??
            0) === 0 && (
          <Grid size={{ xs: 12 }}>
            <Card sx={{ p: 4 }}>
              <Stack spacing={1}>
                <Typography variant="h6">No applications yet</Typography>
                <Typography color="text.secondary">
                  Choose an application below to launch your first instance.
                </Typography>
              </Stack>
            </Card>
          </Grid>
        )}
      </Grid>

      <Box>
        <Typography variant="h5">Available applications</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          Click an app to launch your own instance.
        </Typography>
        <ProductList
          products={deployableProducts}
          selectedProductId={null}
          onSelectProduct={(id) => {
            const product = deployableProducts.find((p) => p.id === id)
            if (product) setDeployProduct(product)
          }}
        />
      </Box>

      {deployProduct && user && (
        <DeployDialog
          product={deployProduct}
          userId={user.id}
          onClose={() => setDeployProduct(null)}
        />
      )}

      {editDeployment && user && editDeployment.desired_template?.product && (
        <DeployDialog
          product={editDeployment.desired_template.product}
          userId={user.id}
          deployment={editDeployment}
          onClose={() => setEditDeployment(null)}
        />
      )}
    </Stack>
  )
}

export default Dashboard
