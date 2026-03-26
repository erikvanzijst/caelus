import { Dialog, DialogContent } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { createDeployment, updateDeployment, listTemplates, listPlans } from '../api/endpoints'
import type { Deployment, Plan, Product, ProductTemplate } from '../api/types'
import { validateUserValues } from './UserValuesForm'
import { DeployDialogContent } from './DeployDialogContent'

interface DeployDialogProps {
  product: Product
  userId: number
  onClose: () => void
  deployment?: Deployment
}

export function DeployDialog({ product, userId, onClose, deployment }: DeployDialogProps) {
  const queryClient = useQueryClient()
  const [userValues, setUserValues] = useState<Record<string, unknown> | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [userValuesErrors, setUserValuesErrors] = useState<string[]>([])
  const [hostnameValid, setHostnameValid] = useState(true)
  const [selectedPlanTemplateId, setSelectedPlanTemplateId] = useState<number | null>(null)

  const isEditMode = Boolean(deployment)

  const templatesQuery = useQuery({
    queryKey: ['templates', product.id],
    queryFn: () => listTemplates(product.id),
    enabled: !isEditMode,
  })

  const plansQuery = useQuery({
    queryKey: ['plans', product.id],
    queryFn: () => listPlans(product.id),
    enabled: !isEditMode,
  })

  const canonicalTemplate: ProductTemplate | undefined = useMemo(() => {
    return templatesQuery.data?.find((t) => t.id === product.template_id)
  }, [templatesQuery.data, product.template_id])

  const activeTemplate: ProductTemplate | undefined = isEditMode
    ? deployment!.desired_template
    : canonicalTemplate

  const plans: Plan[] = useMemo(() => {
    if (isEditMode) {
      // Show the deployment's current plan as a read-only display
      const plan = deployment?.subscription?.plan_template?.plan
      return plan ? [{ ...plan, template: deployment?.subscription?.plan_template ?? null }] : []
    }
    return (plansQuery.data ?? []).filter((p) => p.template_id != null)
  }, [isEditMode, deployment, plansQuery.data])

  // Auto-select if there's only one plan
  const effectivePlanTemplateId = useMemo(() => {
    if (isEditMode) return null
    if (selectedPlanTemplateId) return selectedPlanTemplateId
    if (plans.length === 1 && plans[0].template_id) return plans[0].template_id
    return null
  }, [isEditMode, selectedPlanTemplateId, plans])

  const createMutation = useMutation({
    mutationFn: (payload: { templateId: number; userValuesJson?: object; planTemplateId?: number }) =>
      createDeployment(userId, {
        desired_template_id: payload.templateId,
        user_values_json: payload.userValuesJson,
        plan_template_id: payload.planTemplateId,
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] })
      if (data.checkout_url) {
        window.location.href = data.checkout_url
      } else {
        onClose()
      }
    },
    onError: (error: Error) => {
      const errorMsg = error.message
      if (errorMsg.includes('user_values_json') || errorMsg.includes('validation')) {
        const validationErrors = validateUserValues(
          activeTemplate?.values_schema_json ?? null,
          userValues,
        )
        setUserValuesErrors(validationErrors.length > 0 ? validationErrors : [errorMsg])
      } else {
        setFormError(error.message)
      }
    },
  })

  const updateMutation = useMutation({
    mutationFn: (payload: { templateId: number; userValuesJson?: object }) =>
      updateDeployment(userId, deployment!.id, {
        desired_template_id: payload.templateId,
        user_values_json: payload.userValuesJson,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] })
      onClose()
    },
    onError: (error: Error) => {
      const errorMsg = error.message
      if (errorMsg.includes('not in ready state')) {
        setFormError('This deployment cannot be updated right now. It may be provisioning or was modified by another process.')
      } else if (errorMsg.includes('user_values_json') || errorMsg.includes('validation')) {
        const validationErrors = validateUserValues(
          activeTemplate?.values_schema_json ?? null,
          userValues,
        )
        setUserValuesErrors(validationErrors.length > 0 ? validationErrors : [errorMsg])
      } else {
        setFormError(error.message)
      }
    },
  })

  const activeMutation = isEditMode ? updateMutation : createMutation

  const handleLaunch = useCallback(() => {
    const templateId = isEditMode ? deployment!.desired_template_id : product.template_id
    if (!templateId) return

    if (activeTemplate?.values_schema_json) {
      const validationErrors = validateUserValues(
        activeTemplate.values_schema_json as Record<string, unknown>,
        userValues,
      )
      if (validationErrors.length > 0) {
        setUserValuesErrors(validationErrors)
        return
      }
    }

    setUserValuesErrors([])
    const valuesToSend = userValues ?? {}
    if (isEditMode) {
      updateMutation.mutate({
        templateId,
        userValuesJson: valuesToSend,
      })
    } else {
      createMutation.mutate({
        templateId,
        userValuesJson: valuesToSend,
        planTemplateId: effectivePlanTemplateId ?? undefined,
      })
    }
  }, [product.template_id, deployment, isEditMode, activeTemplate, userValues, effectivePlanTemplateId, createMutation, updateMutation])

  const initialValuesJson = isEditMode
    ? (deployment!.user_values_json as Record<string, unknown> | null) ?? null
    : null

  // Widen dialog when there are multiple plans
  const dialogMaxWidth = !isEditMode && plans.length > 2 ? 'md' as const : 'sm' as const

  return (
    <Dialog open onClose={onClose} maxWidth={dialogMaxWidth} fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <DeployDialogContent
          product={product}
          valuesSchemaJson={
            (activeTemplate?.values_schema_json as Record<string, unknown> | null) ?? null
          }
          initialValuesJson={initialValuesJson}
          onChange={setUserValues}
          onHostnameValidationChange={setHostnameValid}
          onLaunch={handleLaunch}
          onCancel={onClose}
          launchDisabled={
            activeMutation.isPending ||
            !activeTemplate ||
            !hostnameValid ||
            (!isEditMode && !effectivePlanTemplateId)
          }
          launchPending={activeMutation.isPending}
          formError={formError}
          userValuesErrors={userValuesErrors}
          noTemplateWarning={!isEditMode && !templatesQuery.isLoading && !canonicalTemplate}
          loading={!isEditMode && (templatesQuery.isLoading || plansQuery.isLoading)}
          initialHostname={deployment?.hostname ?? undefined}
          submitLabel={isEditMode ? 'Update' : 'Launch'}
          plans={plans}
          selectedPlanTemplateId={isEditMode ? (deployment?.subscription?.plan_template?.id ?? null) : effectivePlanTemplateId}
          onSelectPlan={isEditMode ? undefined : (planTemplateId) => setSelectedPlanTemplateId(planTemplateId)}
        />
      </DialogContent>
    </Dialog>
  )
}
