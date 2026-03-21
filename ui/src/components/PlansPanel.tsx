import { Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { listProducts } from '../api/endpoints'
import type { Product } from '../api/types'
import { useAuth } from '../state/AuthContext'
import { ProductList } from './ProductList'

function readSelectedProduct(): number | null {
  const raw = sessionStorage.getItem('admin.selectedProduct')
  if (raw) { const n = Number(raw); if (!isNaN(n)) return n }
  return null
}

export function PlansPanel() {
  const { user } = useAuth()
  const [selectedProductId, setSelectedProductIdRaw] = useState<number | null>(readSelectedProduct)

  const setSelectedProductId = useCallback((id: number) => {
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
    if (selectedProductId === null) return undefined
    return productsQuery.data?.find((p) => p.id === selectedProductId)
  }, [productsQuery.data, selectedProductId])

  return (
    <Stack spacing={4}>
      <ProductList
        products={productsQuery.data}
        selectedProductId={selectedProductId}
        onSelectProduct={(id) => {
          if (typeof id === 'number') setSelectedProductId(id)
        }}
      />
      {selectedProduct && (
        <Typography color="text.secondary">
          Plans for {selectedProduct.name} will appear here.
        </Typography>
      )}
    </Stack>
  )
}
