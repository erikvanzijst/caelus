import { Alert, Box, Card, Stack, Typography } from '@mui/material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { listProducts } from '../api/endpoints'
import type { Product } from '../api/types'
import { useAuth } from '../state/AuthContext'
import { ProductList } from '../components/ProductList'
import { ProductDetail } from '../components/ProductDetail'
import { NewProductHeader } from '../components/NewProductHeader'

function Admin() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedProductId, setSelectedProductId] = useState<number | 'new' | null>(null)
  const [adminError, setAdminError] = useState<string | null>(null)

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
    enabled: Boolean(user),
  })

  useEffect(() => {
    if (!productsQuery.data?.length) return
    if (!selectedProductId) {
      setSelectedProductId(productsQuery.data[0].id)
    }
  }, [productsQuery.data, selectedProductId])

  const selectedProduct = useMemo<Product | undefined>(() => {
    if (selectedProductId === 'new' || selectedProductId === null) return undefined
    return productsQuery.data?.find((product) => product.id === selectedProductId)
  }, [productsQuery.data, selectedProductId])

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h3">Admin</Typography>
        <Typography color="text.secondary">
          Manage products, template versions, and the canonical template selection.
        </Typography>
      </Box>
      {adminError && <Alert severity="error">{adminError}</Alert>}
      <ProductList
        products={productsQuery.data}
        selectedProductId={selectedProductId}
        onSelectProduct={setSelectedProductId}
        showNewCard
      />
      {selectedProductId === 'new' && (
        <Card>
          <NewProductHeader
            onCreated={(productId) => {
              queryClient.invalidateQueries({ queryKey: ['products'] })
              setSelectedProductId(productId)
            }}
            onError={(error: Error) => setAdminError(error.message)}
          />
        </Card>
      )}
      {selectedProduct && (
        <ProductDetail
          key={selectedProduct.id}
          product={selectedProduct}
          onError={(error: Error) => setAdminError(error.message)}
        />
      )}
    </Stack>
  )
}

export default Admin
