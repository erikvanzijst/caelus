import { Alert, Card, Stack } from '@mui/material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { listProducts } from '../api/endpoints'
import type { Product } from '../api/types'
import { useAuth } from '../state/AuthContext'
import { ProductList } from './ProductList'
import { ProductDetail } from './ProductDetail'
import { NewProductHeader } from './NewProductHeader'

export function ProductsPanel() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [adminError, setAdminError] = useState<string | null>(null)

  const [selectedProductId, setSelectedProductIdRaw] = useState<number | 'new' | null>(() => {
    const raw = sessionStorage.getItem('admin.selectedProduct')
    if (raw) { const n = Number(raw); if (!isNaN(n)) return n }
    return null
  })

  const setSelectedProductId = useCallback((id: number | 'new') => {
    sessionStorage.setItem('admin.selectedProduct', String(id))
    setSelectedProductIdRaw(id)
  }, [])

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
    enabled: Boolean(user),
  })

  const sortedProducts = useMemo(
    () => [...(productsQuery.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [productsQuery.data],
  )

  useEffect(() => {
    if (!sortedProducts.length) return
    if (selectedProductId === null) {
      setSelectedProductId(sortedProducts[0].id)
    }
  }, [sortedProducts, selectedProductId, setSelectedProductId])

  const selectedProduct = useMemo<Product | undefined>(() => {
    if (selectedProductId === 'new' || selectedProductId === null) return undefined
    return productsQuery.data?.find((product) => product.id === selectedProductId)
  }, [productsQuery.data, selectedProductId])

  return (
    <Stack spacing={4}>
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
