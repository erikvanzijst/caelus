import {
  Alert,
  Avatar,
  Box,
  Button,
  Stack,
  Typography,
} from '@mui/material'
import { resolveApiPath } from '../api/client'
import type { Product } from '../api/types'
import { UserValuesForm } from './UserValuesForm'

interface DeployDialogContentProps {
  product: Product
  valuesSchemaJson: Record<string, unknown> | null
  initialValuesJson: Record<string, unknown> | null
  onChange: (userValues: Record<string, unknown> | null) => void
  onHostnameValidationChange?: (valid: boolean) => void
  onLaunch?: () => void
  onCancel?: () => void
  launchDisabled?: boolean
  launchPending?: boolean
  formError?: string | null
  userValuesErrors?: string[]
  noTemplateWarning?: boolean
  loading?: boolean
  initialHostname?: string
  submitLabel?: string
  readOnly?: boolean
}

export function DeployDialogContent({
  product,
  valuesSchemaJson,
  initialValuesJson,
  onChange,
  onHostnameValidationChange,
  onLaunch,
  onCancel,
  launchDisabled,
  launchPending,
  formError,
  userValuesErrors = [],
  noTemplateWarning,
  loading,
  initialHostname,
  submitLabel = 'Launch',
  readOnly,
}: DeployDialogContentProps) {
  return (
    <>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
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
      <Stack spacing={2}>
        {formError && <Alert severity="error">{formError}</Alert>}
        {loading ? (
          <Typography color="text.secondary">Loading template...</Typography>
        ) : noTemplateWarning ? (
          <Alert severity="warning">
            This product has no template configured yet.
          </Alert>
        ) : (
          <UserValuesForm
            valuesSchemaJson={valuesSchemaJson}
            initialValuesJson={initialValuesJson}
            onChange={onChange}
            onHostnameValidationChange={onHostnameValidationChange}
            errors={userValuesErrors}
            initialHostname={initialHostname}
            readOnly={readOnly}
          />
        )}
      </Stack>
      {(onCancel || onLaunch) && (
        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 3 }}>
          {onCancel && <Button onClick={onCancel}>Cancel</Button>}
          {onLaunch && (
            <Button
              variant="contained"
              onClick={onLaunch}
              disabled={launchDisabled}
            >
              {launchPending ? `${submitLabel === 'Launch' ? 'Launching' : 'Updating'}...` : submitLabel}
            </Button>
          )}
        </Stack>
      )}
    </>
  )
}
