import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import Grid from '@mui/material/GridLegacy'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  createDeployment,
  createUser,
  deleteDeployment,
  listDeployments,
  listProducts,
  listUsers,
} from '../api/endpoints'
import type { Product, User } from '../api/types'
import { useAuthEmail } from '../state/useAuthEmail'
import { ensureUrl, formatDateTime } from '../utils/format'

function Dashboard() {
  const queryClient = useQueryClient()
  const { email } = useAuthEmail()
  const [selectedProductId, setSelectedProductId] = useState<number | ''>('')
  const [domainname, setDomainname] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => listUsers(email),
    enabled: Boolean(email),
  })

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(email),
    enabled: Boolean(email),
  })

  const currentUser = useMemo<User | undefined>(() => {
    return usersQuery.data?.find((user) => user.email === email)
  }, [usersQuery.data, email])

  const createUserMutation = useMutation({
    mutationFn: (newEmail: string) => createUser(newEmail, email),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  useEffect(() => {
    if (!email || usersQuery.isLoading || usersQuery.isError) return
    if (!currentUser && !createUserMutation.isPending) {
      createUserMutation.mutate(email)
    }
  }, [email, usersQuery.isLoading, usersQuery.isError, currentUser, createUserMutation])

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

  const deploymentsQuery = useQuery({
    queryKey: ['deployments', currentUser?.id],
    queryFn: () => listDeployments(currentUser!.id, email),
    enabled: Boolean(currentUser?.id),
  })

  const createDeploymentMutation = useMutation({
    mutationFn: (payload: { userId: number; templateId: number; domainname: string }) =>
      createDeployment(payload.userId, { template_id: payload.templateId, domainname: payload.domainname }, email),
    onSuccess: () => {
      setDomainname('')
      setFormError(null)
      queryClient.invalidateQueries({ queryKey: ['deployments'] })
    },
    onError: (error: Error) => setFormError(error.message),
  })

  const deleteDeploymentMutation = useMutation({
    mutationFn: (deploymentId: number) =>
      deleteDeployment(currentUser!.id, deploymentId, email),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deployments'] }),
  })

  const selectedProduct = useMemo<Product | undefined>(() => {
    return availableProducts.find((product) => product.id === selectedProductId)
  }, [availableProducts, selectedProductId])

  const handleCreateDeployment = () => {
    if (!currentUser) return
    if (!selectedProduct?.template_id) {
      setFormError('Select a product with a canonical template set in Admin.')
      return
    }
    if (!domainname.trim()) {
      setFormError('Enter a domain name to continue.')
      return
    }
    createDeploymentMutation.mutate({
      userId: currentUser.id,
      templateId: selectedProduct.template_id,
      domainname: domainname.trim(),
    })
  }

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h3">Your deployments</Typography>
        <Typography color="text.secondary">
          Spin up new instances from products and keep track of live environments.
        </Typography>
      </Box>

      <Card sx={{ p: 1 }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h5">Create deployment</Typography>
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
              <TextField
                fullWidth
                label="Domain name"
                placeholder="app.example.com"
                value={domainname}
                onChange={(event) => setDomainname(event.target.value)}
              />
              <Button
                variant="contained"
                onClick={handleCreateDeployment}
                disabled={createDeploymentMutation.isPending || !currentUser || !availableProducts.length}
              >
                Launch
              </Button>
            </Stack>
            {selectedProduct && (
              <Typography color="text.secondary" variant="body2">
                Canonical template:{' '}
                {selectedProduct.template_id ? `#${selectedProduct.template_id}` : 'Not set'}
              </Typography>
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
        {deploymentsQuery.data?.map((deployment) => (
          <Grid item xs={12} md={6} key={deployment.id}>
            <Card>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6">{deployment.domainname}</Typography>
                    <Chip
                      label={deployment.template?.product?.name ?? 'Unknown product'}
                      color="primary"
                      variant="outlined"
                    />
                  </Stack>
                  <Typography color="text.secondary">
                    Created {formatDateTime(deployment.created_at)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Template #{deployment.template_id}
                  </Typography>
                </Stack>
              </CardContent>
              <CardActions sx={{ px: 2, pb: 2 }}>
                <Button
                  href={ensureUrl(deployment.domainname)}
                  target="_blank"
                  rel="noreferrer"
                  variant="contained"
                >
                  Open
                </Button>
                <Button
                  variant="outlined"
                  color="secondary"
                  onClick={() => {
                    if (window.confirm('Delete this deployment?')) {
                      deleteDeploymentMutation.mutate(deployment.id)
                    }
                  }}
                >
                  Delete
                </Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
        {!deploymentsQuery.isLoading && deploymentsQuery.data?.length === 0 && (
          <Grid item xs={12}>
            <Card sx={{ p: 4 }}>
              <Stack spacing={1}>
                <Typography variant="h6">No deployments yet</Typography>
                <Typography color="text.secondary">
                  Choose a product and domain to launch your first instance.
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
