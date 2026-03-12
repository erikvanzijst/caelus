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
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  createDeployment,
  deleteDeployment,
  listDeployments,
  listProducts,
  listTemplates,
} from '../api/endpoints'
import type { Product, ProductTemplate } from '../api/types'
import { resolveApiPath } from '../api/client'
import { useAuth } from '../state/AuthContext'
import { isTransitionalStatus, statusColor } from '../utils/deploymentStatus'
import { ensureUrl, formatDateTime } from '../utils/format'
import { UserValuesForm, validateUserValues } from '../components/UserValuesForm'

function Dashboard() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [selectedProductId, setSelectedProductId] = useState<number | ''>('')
  const [userValues, setUserValues] = useState<Record<string, unknown> | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [userValuesErrors, setUserValuesErrors] = useState<string[]>([])
  const [deletePendingIds, setDeletePendingIds] = useState<Set<number>>(new Set())

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
    enabled: Boolean(user),
  })

  const availableProducts = useMemo<Product[]>(() => {
    return (productsQuery.data ?? []).filter((product) => Boolean(product.template_id))
  }, [productsQuery.data])

  useEffect(() => {
    if (!availableProducts.length) {
      if (selectedProductId !== '') setSelectedProductId('')
      return
    }
    if (selectedProductId === '') {
      setSelectedProductId(availableProducts[0].id)
    }
  }, [availableProducts, selectedProductId])

  const selectedProduct = useMemo<Product | undefined>(() => {
    return availableProducts.find((product) => product.id === selectedProductId)
  }, [availableProducts, selectedProductId])

  const canonicalTemplateQuery = useQuery({
    queryKey: ['templates', selectedProductId],
    queryFn: () => listTemplates(selectedProductId as number),
    enabled: Boolean(selectedProductId),
  })

  const canonicalTemplate: ProductTemplate | undefined = useMemo(() => {
    return canonicalTemplateQuery.data?.find((t) => t.id === selectedProduct?.template_id)
  }, [canonicalTemplateQuery.data, selectedProduct?.template_id])

  const deploymentsQuery = useQuery({
    queryKey: ['deployments', user?.id],
    queryFn: () => listDeployments(user!.id),
    enabled: Boolean(user?.id),
    refetchInterval: (query) => {
      const items = query.state.data ?? []
      return items.some((deployment) => isTransitionalStatus(deployment.status)) ? 3000 : false
    },
  })

  const createDeploymentMutation = useMutation({
    mutationFn: (payload: { userId: number; templateId: number; userValuesJson?: object }) =>
      createDeployment(
        payload.userId,
        { desired_template_id: payload.templateId, user_values_json: payload.userValuesJson },
      ),
    onSuccess: () => {
      setUserValues(null)
      setFormError(null)
      setUserValuesErrors([])
      queryClient.invalidateQueries({ queryKey: ['deployments'] })
    },
    onError: (error: Error) => {
      const errorMsg = error.message
      if (errorMsg.includes('user_values_json') || errorMsg.includes('validation')) {
        const validationErrors = validateUserValues(
          canonicalTemplate?.values_schema_json ?? null,
          userValues,
        )
        setUserValuesErrors(validationErrors.length > 0 ? validationErrors : [errorMsg])
      } else {
        setFormError(error.message)
      }
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

  const handleCreateDeployment = () => {
    if (!user) return
    if (!selectedProduct?.template_id) {
      setFormError('Select a product with a canonical template set in Admin.')
      return
    }

    // Validate user values against schema
    if (canonicalTemplate?.values_schema_json) {
      const validationErrors = validateUserValues(
        canonicalTemplate.values_schema_json as Record<string, unknown>,
        userValues,
      )
      if (validationErrors.length > 0) {
        setUserValuesErrors(validationErrors)
        return
      }
    }

    setUserValuesErrors([])
    const valuesToSend = userValues ?? canonicalTemplate?.default_values_json ?? undefined
    createDeploymentMutation.mutate({
      userId: user.id,
      templateId: selectedProduct.template_id,
      userValuesJson: valuesToSend,
    })
  }

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h3">Your applications</Typography>
        <Typography color="text.secondary">
          Spin up new products and keep track of your live environments.
        </Typography>
      </Box>

      <Card sx={{ p: 1 }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h5">Deploy an application</Typography>
            {formError && <Alert severity="error">{formError}</Alert>}
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <Select
                fullWidth
                value={selectedProductId}
                onChange={(event) => setSelectedProductId(Number(event.target.value))}
                displayEmpty
                disabled={!availableProducts.length}
              >
                {availableProducts.map((product) => (
                  <MenuItem value={product.id} key={product.id}>
                    {product.name}
                  </MenuItem>
                ))}
              </Select>
              <Button
                variant="contained"
                onClick={handleCreateDeployment}
                disabled={createDeploymentMutation.isPending || !user || !availableProducts.length}
              >
                Launch
              </Button>
            </Stack>
            {selectedProduct && canonicalTemplate && (
              <>
                {canonicalTemplateQuery.isLoading ? (
                  <Typography color="text.secondary">Loading template...</Typography>
                ) : (
                  <UserValuesForm
                    valuesSchemaJson={canonicalTemplate.values_schema_json as Record<string, unknown> | null}
                    defaultValuesJson={canonicalTemplate.default_values_json as Record<string, unknown> | null}
                    onChange={setUserValues}
                    errors={userValuesErrors}
                  />
                )}
              </>
            )}
            {!availableProducts.length && (
              <Alert severity="info">
                No products are available for deployment yet. Set a canonical template in Admin.
              </Alert>
            )}
          </Stack>
        </CardContent>
      </Card>

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
                      <Typography variant="h6" noWrap>{deployment.domainname}</Typography>
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
                <Button
                  href={deployment.domainname && !isTransitionalStatus(deployment.status) ? ensureUrl(deployment.domainname) : undefined}
                  target="_blank"
                  rel="noreferrer"
                  variant="contained"
                  disabled={!deployment.domainname || isTransitionalStatus(deployment.status)}
                >
                  Open
                </Button>
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
                  Choose a product to launch your first instance.
                </Typography>
              </Stack>
            </Card>
          </Grid>
        )}
      </Grid>
    </Stack>
  )
}

export default Dashboard
