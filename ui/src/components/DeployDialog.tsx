import {
  Alert,
  Avatar,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { createDeployment, listTemplates } from '../api/endpoints'
import { resolveApiPath } from '../api/client'
import type { Product, ProductTemplate } from '../api/types'
import { UserValuesForm, validateUserValues } from './UserValuesForm'

interface DeployDialogProps {
  product: Product
  userId: number
  onClose: () => void
}

export function DeployDialog({ product, userId, onClose }: DeployDialogProps) {
  const queryClient = useQueryClient()
  const [userValues, setUserValues] = useState<Record<string, unknown> | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [userValuesErrors, setUserValuesErrors] = useState<string[]>([])
  const [hostnameValid, setHostnameValid] = useState(true)

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

  const handleLaunch = useCallback(() => {
    if (!product.template_id) return

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
    createMutation.mutate({
      templateId: product.template_id,
      userValuesJson: valuesToSend,
    })
  }, [product.template_id, canonicalTemplate, userValues, createMutation])

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar
            src={product.icon_url ? resolveApiPath(product.icon_url) : undefined}
            alt={product.name}
            variant="rounded"
            sx={{ width: 48, height: 48 }}
          >
            {product.name[0]}
          </Avatar>
          <Box>
            <Typography variant="h6">{product.name}</Typography>
            {product.description && (
              <Typography variant="body2" color="text.secondary">
                {product.description}
              </Typography>
            )}
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {formError && <Alert severity="error">{formError}</Alert>}
          {templatesQuery.isLoading ? (
            <Typography color="text.secondary">Loading template...</Typography>
          ) : canonicalTemplate ? (
            <UserValuesForm
              valuesSchemaJson={canonicalTemplate.values_schema_json as Record<string, unknown> | null}
              defaultValuesJson={canonicalTemplate.default_values_json as Record<string, unknown> | null}
              onChange={setUserValues}
              onHostnameValidationChange={setHostnameValid}
              errors={userValuesErrors}
            />
          ) : (
            <Alert severity="warning">
              This product has no template configured yet.
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleLaunch}
          disabled={createMutation.isPending || !canonicalTemplate || !hostnameValid}
        >
          {createMutation.isPending ? 'Launching...' : 'Launch'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
