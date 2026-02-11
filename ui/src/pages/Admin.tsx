import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import Grid from '@mui/material/GridLegacy'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  createProduct,
  createTemplate,
  deleteProduct,
  deleteTemplate,
  listProducts,
  listTemplates,
  updateProductTemplate,
} from '../api/endpoints'
import type { Product } from '../api/types'
import { useAuthEmail } from '../state/useAuthEmail'
import { formatDateTime } from '../utils/format'

function Admin() {
  const { email } = useAuthEmail()
  const queryClient = useQueryClient()
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null)
  const [productName, setProductName] = useState('')
  const [productDescription, setProductDescription] = useState('')
  const [templateUrl, setTemplateUrl] = useState('')
  const [adminError, setAdminError] = useState<string | null>(null)

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(email),
    enabled: Boolean(email),
  })

  useEffect(() => {
    if (!productsQuery.data?.length) return
    if (!selectedProductId) {
      setSelectedProductId(productsQuery.data[0].id)
    }
  }, [productsQuery.data, selectedProductId])

  const selectedProduct = useMemo<Product | undefined>(() => {
    return productsQuery.data?.find((product) => product.id === selectedProductId)
  }, [productsQuery.data, selectedProductId])

  const templatesQuery = useQuery({
    queryKey: ['templates', selectedProductId],
    queryFn: () => listTemplates(selectedProductId!, email),
    enabled: Boolean(selectedProductId),
  })

  const createProductMutation = useMutation({
    mutationFn: () =>
      createProduct(
        {
          name: productName.trim(),
          description: productDescription.trim() || null,
        },
        email,
      ),
    onSuccess: () => {
      setProductName('')
      setProductDescription('')
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
    onError: (error: Error) => setAdminError(error.message),
  })

  const deleteProductMutation = useMutation({
    mutationFn: (productId: number) => deleteProduct(productId, email),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
  })

  const createTemplateMutation = useMutation({
    mutationFn: () =>
      createTemplate(
        selectedProductId!,
        { docker_image_url: templateUrl.trim() || null },
        email,
      ),
    onSuccess: (template) => {
      setTemplateUrl('')
      queryClient.invalidateQueries({ queryKey: ['templates', selectedProductId] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      if (!selectedProduct?.template_id) {
        updateCanonicalMutation.mutate(template.id)
      }
    },
    onError: (error: Error) => setAdminError(error.message),
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (payload: { templateId: number; wasCanonical: boolean }) =>
      deleteTemplate(selectedProductId!, payload.templateId, email).then(() => payload),
    onSuccess: async (payload) => {
      queryClient.invalidateQueries({ queryKey: ['templates', selectedProductId] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      if (!payload.wasCanonical) return
      const templates = await queryClient.fetchQuery({
        queryKey: ['templates', selectedProductId],
        queryFn: () => listTemplates(selectedProductId!, email),
      })
      const newest = [...templates].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )[0]
      if (newest) {
        updateCanonicalMutation.mutate(newest.id)
      }
    },
  })

  const updateCanonicalMutation = useMutation({
    mutationFn: (templateId: number) =>
      updateProductTemplate(selectedProductId!, templateId, email),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
    onError: (error: Error) => setAdminError(error.message),
  })

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h3">Admin</Typography>
        <Typography color="text.secondary">
          Manage products, template versions, and the canonical template selection.
        </Typography>
      </Box>
      {adminError && <Alert severity="error">{adminError}</Alert>}
      <Grid container spacing={3}>
        <Grid item xs={12} md={5}>
          <Stack spacing={2}>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Create product</Typography>
                  <TextField
                    label="Product name"
                    value={productName}
                    onChange={(event) => setProductName(event.target.value)}
                  />
                  <TextField
                    label="Description"
                    multiline
                    minRows={3}
                    value={productDescription}
                    onChange={(event) => setProductDescription(event.target.value)}
                  />
                </Stack>
              </CardContent>
              <CardActions sx={{ px: 2, pb: 2 }}>
                <Button
                  variant="contained"
                  disabled={!productName.trim() || createProductMutation.isPending}
                  onClick={() => {
                    setAdminError(null)
                    createProductMutation.mutate()
                  }}
                >
                  Add product
                </Button>
              </CardActions>
            </Card>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Products</Typography>
                  {productsQuery.data?.map((product) => (
                    <Box
                      key={product.id}
                      onClick={() => setSelectedProductId(product.id)}
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        border: '1px solid rgba(148, 163, 184, 0.2)',
                        cursor: 'pointer',
                        bgcolor:
                          selectedProductId === product.id ? 'rgba(37,99,235,0.08)' : 'transparent',
                      }}
                    >
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle1">{product.name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {product.description || 'No description'}
                        </Typography>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Chip
                            label={
                              product.template_id
                                ? `Canonical template #${product.template_id}`
                                : 'No canonical template'
                            }
                            size="small"
                            color={product.template_id ? 'primary' : 'default'}
                            variant="outlined"
                          />
                        </Stack>
                      </Stack>
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
        <Grid item xs={12} md={7}>
          <Stack spacing={2}>
            <Card>
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="h6">Selected product</Typography>
                  <Typography variant="h5">{selectedProduct?.name ?? 'Pick a product'}</Typography>
                  <Typography color="text.secondary">
                    {selectedProduct?.description || 'No description provided.'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Created {formatDateTime(selectedProduct?.created_at)}
                  </Typography>
                </Stack>
              </CardContent>
              <CardActions sx={{ px: 2, pb: 2 }}>
                <Button
                  variant="outlined"
                  color="secondary"
                  disabled={!selectedProduct}
                  onClick={() => {
                    if (!selectedProduct) return
                    if (window.confirm(`Delete ${selectedProduct.name}?`)) {
                      deleteProductMutation.mutate(selectedProduct.id)
                    }
                  }}
                >
                  Delete product
                </Button>
              </CardActions>
            </Card>

            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Create template version</Typography>
                  <TextField
                    label="Docker image URL"
                    placeholder="ghcr.io/org/app:latest"
                    value={templateUrl}
                    onChange={(event) => setTemplateUrl(event.target.value)}
                    disabled={!selectedProductId}
                  />
                </Stack>
              </CardContent>
              <CardActions sx={{ px: 2, pb: 2 }}>
                <Button
                  variant="contained"
                  disabled={!selectedProductId || createTemplateMutation.isPending}
                  onClick={() => {
                    setAdminError(null)
                    createTemplateMutation.mutate()
                  }}
                >
                  Add template
                </Button>
              </CardActions>
            </Card>

            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Template versions</Typography>
                  <Divider />
                  {templatesQuery.data?.map((template) => (
                    <Box
                      key={template.id}
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        border: '1px solid rgba(148, 163, 184, 0.2)',
                      }}
                    >
                      <Stack spacing={1}>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Typography variant="subtitle1">Template #{template.id}</Typography>
                          {selectedProduct?.template_id === template.id && (
                            <Chip label="Canonical" color="primary" size="small" />
                          )}
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                          {template.docker_image_url || 'No image URL'}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Created {formatDateTime(template.created_at)}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Button
                            variant="outlined"
                            onClick={() => updateCanonicalMutation.mutate(template.id)}
                          >
                            Set canonical
                          </Button>
                          <Button
                            variant="outlined"
                            color="secondary"
                            onClick={() => {
                              if (window.confirm('Delete this template version?')) {
                                setAdminError(null)
                                deleteTemplateMutation.mutate({
                                  templateId: template.id,
                                  wasCanonical: selectedProduct?.template_id === template.id,
                                })
                              }
                            }}
                          >
                            Delete
                          </Button>
                        </Stack>
                      </Stack>
                    </Box>
                  ))}
                  {!templatesQuery.isLoading && templatesQuery.data?.length === 0 && (
                    <Typography color="text.secondary">
                      No templates yet. Add the first version to unlock deployments.
                    </Typography>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  )
}

export default Admin
