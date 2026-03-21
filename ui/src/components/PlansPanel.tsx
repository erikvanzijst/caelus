import { Alert, Card, Divider, Stack, Typography } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { createPlan, deletePlan, listPlanTemplates, listPlans, listProducts, updatePlan } from '../api/endpoints'
import type { Plan, Product } from '../api/types'
import { useAuth } from '../state/AuthContext'
import { ProductList } from './ProductList'
import { PlanCards } from './PlanCards'
import { PlanTemplateTabs } from './PlanTemplateTabs'

function readSelectedProduct(): number | null {
  const raw = sessionStorage.getItem('admin.selectedProduct')
  if (raw) { const n = Number(raw); if (!isNaN(n)) return n }
  return null
}

export function PlansPanel() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedProductId, setSelectedProductIdRaw] = useState<number | null>(readSelectedProduct)
  const [selectedPlanId, setSelectedPlanId] = useState<number | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const setSelectedProductId = useCallback((id: number) => {
    sessionStorage.setItem('admin.selectedProduct', String(id))
    setSelectedProductIdRaw(id)
    setSelectedPlanId(null)
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

  const plansQuery = useQuery({
    queryKey: ['plans', selectedProductId],
    queryFn: () => listPlans(selectedProductId!),
    enabled: selectedProductId !== null,
  })

  const selectedPlan = useMemo<Plan | undefined>(() => {
    if (selectedPlanId === null || selectedPlanId === 'new') return undefined
    return plansQuery.data?.find((p) => p.id === selectedPlanId)
  }, [plansQuery.data, selectedPlanId])

  // Auto-select first plan when plans load
  useEffect(() => {
    if (!plansQuery.data?.length) return
    if (selectedPlanId === null) {
      setSelectedPlanId(plansQuery.data[0].id)
    }
  }, [plansQuery.data, selectedPlanId])

  const createPlanMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) =>
      createPlan(selectedProductId!, {
        name: data.name,
        description: data.description || null,
        sort_order: ((plansQuery.data ?? []).reduce((max, p) => Math.max(max, p.sort_order ?? 0), 0)) + 1000,
      }),
    onSuccess: (newPlan) => {
      queryClient.invalidateQueries({ queryKey: ['plans', selectedProductId] })
      setSelectedPlanId(newPlan.id)
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const updatePlanMutation = useMutation({
    mutationFn: ({ planId, data }: { planId: number; data: { name: string; description: string } }) =>
      updatePlan(planId, { name: data.name, description: data.description || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans', selectedProductId] })
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const reorderPlanMutation = useMutation({
    mutationFn: ({ planId, sortOrder }: { planId: number; sortOrder: number }) =>
      updatePlan(planId, { sort_order: sortOrder }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans', selectedProductId] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const deletePlanMutation = useMutation({
    mutationFn: (planId: number) => deletePlan(planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans', selectedProductId] })
      setSelectedPlanId(null)
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const planTemplatesQuery = useQuery({
    queryKey: ['plan-templates', selectedPlan?.id],
    queryFn: () => listPlanTemplates(selectedPlan!.id),
    enabled: selectedPlan !== undefined,
  })

  const saving = createPlanMutation.isPending || updatePlanMutation.isPending

  return (
    <Stack spacing={3}>
      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

      <ProductList
        products={productsQuery.data}
        selectedProductId={selectedProductId}
        onSelectProduct={(id) => {
          if (typeof id === 'number') setSelectedProductId(id)
        }}
      />

      {selectedProduct && (
        <>
          <Divider />
          <Typography variant="h6">
            Plans for {selectedProduct.name}
          </Typography>
          <PlanCards
            plans={plansQuery.data ?? []}
            selectedPlanId={selectedPlanId}
            onSelectPlan={setSelectedPlanId}
            onCreatePlan={(data) => createPlanMutation.mutate(data)}
            onUpdatePlan={(planId, data) => updatePlanMutation.mutate({ planId, data })}
            onDeletePlan={(planId) => deletePlanMutation.mutate(planId)}
            onReorder={(planId, sortOrder) => reorderPlanMutation.mutate({ planId, sortOrder })}
            saving={saving}
          />
        </>
      )}

      {selectedPlan && (
        <>
          <Divider />
          <Card>
            <PlanTemplateTabs
              plan={selectedPlan}
              templates={planTemplatesQuery.data ?? []}
              onError={(err) => setError(err.message)}
            />
          </Card>
        </>
      )}
    </Stack>
  )
}
