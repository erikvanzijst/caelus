import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import {
  Box,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormHelperText,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listDomains } from '../api/endpoints'
import { HostnameField } from './HostnameField'

const ajv = new Ajv2020({ allErrors: true, strict: false })
addFormats(ajv)

export interface SchemaField {
  path: string
  name: string
  type: string
  title?: string
  description?: string
  pattern?: string
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  default?: unknown
  required: boolean
}

export function flattenSchema(
  schema: Record<string, unknown> | null,
  prefix = '',
  requiredPaths: string[] = [],
): SchemaField[] {
  if (!schema || typeof schema !== 'object') {
    return []
  }

  const fields: SchemaField[] = []
  const properties = schema.properties as Record<string, unknown> | undefined
  const schemaRequired = (schema.required as string[]) || []

  if (!properties) {
    return fields
  }

  for (const [key, value] of Object.entries(properties)) {
    const currentPath = prefix ? `${prefix}.${key}` : key
    const isRequired = schemaRequired.includes(key)

    if (isRequired) {
      requiredPaths.push(currentPath)
    }

    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      continue
    }

    const propSchema = value as Record<string, unknown>

    // If it has nested properties, it's an object type - recurse
    if (propSchema.properties) {
      fields.push(...flattenSchema(propSchema, currentPath, requiredPaths))
      continue
    }

    // It's a leaf field - add it
    fields.push({
      path: currentPath,
      name: (propSchema.title as string) || currentPath,
      type: (propSchema.type as string) || 'string',
      title: propSchema.title as string | undefined,
      description: propSchema.description as string | undefined,
      pattern: propSchema.pattern as string | undefined,
      minLength: propSchema.minLength as number | undefined,
      maxLength: propSchema.maxLength as number | undefined,
      minimum: propSchema.minimum as number | undefined,
      maximum: propSchema.maximum as number | undefined,
      default: propSchema.default,
      required: requiredPaths.includes(currentPath),
    })
  }

  return fields
}

export function flattenValues(
  defaults: Record<string, unknown> | null,
  prefix = '',
): Record<string, unknown> {
  if (!defaults || typeof defaults !== 'object') {
    return {}
  }

  const result: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(defaults)) {
    const currentPath = prefix ? `${prefix}.${key}` : key

    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      Object.assign(result, flattenValues(value as Record<string, unknown>, currentPath))
    } else {
      result[currentPath] = value
    }
  }

  return result
}

export function unflatten(values: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(values)) {
    const parts = key.split('.')
    let current = result

    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i]
      if (!(part in current)) {
        current[part] = {}
      }
      current = current[part] as Record<string, unknown>
    }

    current[parts[parts.length - 1]] = value
  }

  return result
}

interface UserValuesFormProps {
  valuesSchemaJson: Record<string, unknown> | null
  initialValuesJson?: Record<string, unknown> | null
  onChange: (userValues: Record<string, unknown> | null) => void
  onHostnameValidationChange?: (valid: boolean) => void
  errors?: string[]
  initialHostname?: string
}

export function UserValuesForm({
  valuesSchemaJson,
  initialValuesJson,
  onChange,
  onHostnameValidationChange,
  errors = [],
  initialHostname,
}: UserValuesFormProps) {
  const fields = useMemo(() => flattenSchema(valuesSchemaJson), [valuesSchemaJson])
  const initialValues = useMemo(() => flattenValues(initialValuesJson ?? null), [initialValuesJson])

  const hasHostnameField = useMemo(
    () => fields.some((f) => f.title?.toLowerCase() === 'hostname'),
    [fields],
  )
  const domainsQuery = useQuery({
    queryKey: ['domains'],
    queryFn: listDomains,
    enabled: hasHostnameField,
    staleTime: 5 * 60 * 1000,
  })

  const [formData, setFormData] = useState<Record<string, unknown>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    const initialData: Record<string, unknown> = {}
    for (const field of fields) {
      const defaultValue = field.path in initialValues ? initialValues[field.path] : field.default
      if (defaultValue !== undefined) {
        if (field.type === 'boolean') {
          initialData[field.path] = Boolean(defaultValue)
        } else {
          initialData[field.path] = defaultValue
        }
      } else if (field.type === 'boolean') {
        initialData[field.path] = false
      }
    }
    setFormData(initialData)
  }, [fields, initialValues])

  useEffect(() => {
    if (fields.length === 0) {
      onChange(null)
      return
    }

    const hasValues = Object.values(formData).some((v) => {
      if (typeof v === 'string') {
        return v !== ''
      }
      return v !== undefined && v !== null
    })
    if (!hasValues) {
      onChange(null)
      return
    }

    const unflattened = unflatten(formData)
    onChange(unflattened)
  }, [formData, fields, onChange])

  useEffect(() => {
    if (errors.length > 0) {
      const newErrors: Record<string, string> = {}
      for (const error of errors) {
        // Try to match error to field
        for (const field of fields) {
          if (error.toLowerCase().includes(field.path.toLowerCase())) {
            newErrors[field.path] = error
            break
          }
        }
      }
      setFieldErrors(newErrors)
    }
  }, [errors, fields])

  const handleChange = (path: string, value: unknown, fieldType: string) => {
    let processedValue = value

    if (fieldType === 'boolean') {
      processedValue = value === true || value === 'true'
    }

    setFormData((prev) => ({ ...prev, [path]: processedValue }))

    // Clear error when user starts typing
    if (fieldErrors[path]) {
      setFieldErrors((prev) => {
        const next = { ...prev }
        delete next[path]
        return next
      })
    }
  }

  if (fields.length === 0) {
    return null
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Configure application values:
      </Typography>
      {errors.length > 0 && Object.keys(fieldErrors).length === 0 && (
        <Box sx={{ p: 1, bgcolor: 'error.light', borderRadius: 1 }}>
          {errors.map((error, i) => (
            <Typography key={i} variant="body2" color="error.contrastText">
              {error}
            </Typography>
          ))}
        </Box>
      )}
      {fields.map((field) => {
        if (field.title?.toLowerCase() === 'hostname') {
          return (
            <HostnameField
              key={field.path}
              value={typeof formData[field.path] === 'string' ? (formData[field.path] as string) : ''}
              onChange={(hostname) => handleChange(field.path, hostname, 'string')}
              onValidationChange={onHostnameValidationChange}
              wildcardDomains={domainsQuery.data ?? []}
              required={field.required}
              error={fieldErrors[field.path]}
              description={field.description}
              initialHostname={initialHostname}
            />
          )
        }

        return (
          <FormControl key={field.path} fullWidth error={!!fieldErrors[field.path]}>
            {field.type === 'boolean' ? (
              <>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={formData[field.path] === true}
                      onChange={(e) => handleChange(field.path, e.target.checked, 'boolean')}
                    />
                  }
                  label={field.title || field.path}
                />
                {field.description && !fieldErrors[field.path] && (
                  <FormHelperText>{field.description}</FormHelperText>
                )}
              </>
            ) : (
              <TextField
                label={field.title || field.path}
                helperText={fieldErrors[field.path] || field.description}
                value={
                  typeof formData[field.path] === 'string' || typeof formData[field.path] === 'number'
                    ? formData[field.path]
                    : ''
                }
                onChange={(e) => handleChange(field.path, e.target.value, field.type)}
                type={
                  field.type === 'integer' || field.type === 'number'
                    ? 'number'
                    : field.pattern
                      ? 'text'
                      : 'text'
                }
                inputProps={
                  field.pattern
                    ? { title: field.description || field.title || field.path }
                    : undefined
                }
                required={field.required}
                error={!!fieldErrors[field.path]}
              />
            )}
            {fieldErrors[field.path] && <FormHelperText>{fieldErrors[field.path]}</FormHelperText>}
          </FormControl>
        )
      })}
    </Stack>
  )
}

export function validateUserValues(
  valuesSchemaJson: Record<string, unknown> | null,
  userValues: Record<string, unknown> | null,
): string[] {
  if (!valuesSchemaJson || !userValues) {
    return []
  }

  const validate = ajv.compile(valuesSchemaJson)
  const valid = validate(userValues)

  if (valid) {
    return []
  }

  return (validate.errors || []).map((err) => {
    const path = err.instancePath || '/'
    return `${path}: ${err.message}`
  })
}
