import { Dialog, DialogContent } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { createDeployment, updateDeployment, listTemplates } from '../api/endpoints'
import type { Deployment, Product, ProductTemplate } from '../api/types'
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

  const isEditMode = Boolean(deployment)

  const templatesQuery = useQuery({
    queryKey: ['templates', product.id],
    queryFn: () => listTemplates(product.id),
  })

  const canonicalTemplate: ProductTemplate | undefined = useMemo(() => {
    return templatesQuery.data?.find((t) => t.id === product.template_id)
  }, [templatesQuery.data, product.template_id])

  const createMutation = useMutation({
    mutationFn: (payload: { templateId: number; userValuesJson?: object }) =>
      createDeployment(userId, {
        desired_template_id: payload.templateId,
        user_values_json: payload.userValuesJson,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] })
      onClose()
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
          canonicalTemplate?.values_schema_json ?? null,
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
    const valuesToSend = userValues ?? {}
    activeMutation.mutate({
      templateId,
      userValuesJson: valuesToSend,
    })
  }, [product.template_id, deployment, isEditMode, canonicalTemplate, userValues, activeMutation])

  // In edit mode, pre-populate the form with the deployment's current user values
  const defaultValuesJson = isEditMode
    ? (deployment!.user_values_json as Record<string, unknown> | null) ?? null
    : (canonicalTemplate?.default_values_json as Record<string, unknown> | null) ?? null

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <DeployDialogContent
          product={product}
          valuesSchemaJson={
            (canonicalTemplate?.values_schema_json as Record<string, unknown> | null) ?? null
          }
          defaultValuesJson={defaultValuesJson}
          onChange={setUserValues}
          onHostnameValidationChange={setHostnameValid}
          onLaunch={handleLaunch}
          onCancel={onClose}
          launchDisabled={activeMutation.isPending || !canonicalTemplate || !hostnameValid}
          launchPending={activeMutation.isPending}
          formError={formError}
          userValuesErrors={userValuesErrors}
          noTemplateWarning={!templatesQuery.isLoading && !canonicalTemplate}
          loading={templatesQuery.isLoading}
          initialHostname={deployment?.hostname ?? undefined}
          submitLabel={isEditMode ? 'Update' : 'Launch'}
        />
      </DialogContent>
    </Dialog>
  )
}
