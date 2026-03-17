import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box, Button, Stack, TextField, Typography } from '@mui/material'
import { SplitPane } from './SplitPane'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import Editor from '@monaco-editor/react'
import type { Product, ProductTemplate } from '../api/types'
import { DeployDialogContent } from './DeployDialogContent'

const DEFAULT_VALUES_SCHEMA = `{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
  },
  "additionalProperties": false
}`

const editorBoxSx = {
  border: '1px solid rgba(148, 163, 184, 0.3)',
  borderRadius: 1,
  overflow: 'hidden',
  resize: 'vertical' as const,
  minHeight: 100,
  maxHeight: 600,
  cursor: 'se-resize',
}

const editorOptions = {
  minimap: { enabled: false },
  lineNumbers: 'on' as const,
  folding: false,
  wordWrap: 'off' as const,
  scrollBeyondLastLine: false,
  fontSize: 13,
  renderLineHighlight: 'none' as const,
  automaticLayout: true,
}

interface TemplateTabNewProps {
  product: Product
  templates: ProductTemplate[]
  onSave: (payload: {
    chart_ref: string
    chart_version: string
    values_schema_json?: object
    system_values_json?: object
  }) => void
  saving?: boolean
}

export function TemplateTabNew({
  product,
  templates,
  onSave,
  saving,
}: TemplateTabNewProps) {
  const newest = useMemo(() => {
    if (templates.length === 0) return null
    return [...templates].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0]
  }, [templates])

  const [chartRef, setChartRef] = useState('')
  const [chartVersion, setChartVersion] = useState('')
  const [schemaText, setSchemaText] = useState('')
  const [defaultsText, setDefaultsText] = useState('')
  const [schemaValid, setSchemaValid] = useState(true)
  const [defaultsValid, setDefaultsValid] = useState(true)
  const [validSchema, setValidSchema] = useState<Record<string, unknown> | null>(null)
  const [validDefaults, setValidDefaults] = useState<Record<string, unknown> | null>(null)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Pre-populate from newest template or defaults
  useEffect(() => {
    if (newest) {
      setChartRef(newest.chart_ref)
      setChartVersion('')
      const schema = newest.values_schema_json
        ? JSON.stringify(newest.values_schema_json, null, 2)
        : DEFAULT_VALUES_SCHEMA
      setSchemaText(schema)
      try {
        setValidSchema(JSON.parse(schema))
        setSchemaValid(true)
      } catch {
        setValidSchema(null)
        setSchemaValid(false)
      }
      const defaults = newest.system_values_json
        ? JSON.stringify(newest.system_values_json, null, 2)
        : ''
      setDefaultsText(defaults)
      if (defaults.trim()) {
        try {
          setValidDefaults(JSON.parse(defaults))
          setDefaultsValid(true)
        } catch {
          setValidDefaults(null)
          setDefaultsValid(false)
        }
      } else {
        setValidDefaults(null)
        setDefaultsValid(true)
      }
    } else {
      setChartRef('')
      setChartVersion('')
      setSchemaText(DEFAULT_VALUES_SCHEMA)
      try {
        setValidSchema(JSON.parse(DEFAULT_VALUES_SCHEMA))
      } catch {
        setValidSchema(null)
      }
      setSchemaValid(true)
      setDefaultsText('')
      setValidDefaults(null)
      setDefaultsValid(true)
    }
  }, [newest])

  const handleSchemaChange = useCallback((value: string | undefined) => {
    const text = value || ''
    setSchemaText(text)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (!text.trim()) {
        setSchemaValid(true)
        setValidSchema(null)
        return
      }
      try {
        const parsed = JSON.parse(text)
        setSchemaValid(true)
        setValidSchema(parsed)
      } catch {
        setSchemaValid(false)
      }
    }, 300)
  }, [])

  const handleDefaultsChange = useCallback((value: string | undefined) => {
    const text = value || ''
    setDefaultsText(text)
    if (!text.trim()) {
      setDefaultsValid(true)
      setValidDefaults(null)
      return
    }
    try {
      const parsed = JSON.parse(text)
      setDefaultsValid(true)
      setValidDefaults(parsed)
    } catch {
      setDefaultsValid(false)
    }
  }, [])

  const canSave =
    chartRef.trim() !== '' &&
    chartVersion.trim() !== '' &&
    schemaValid &&
    defaultsValid &&
    !saving

  const handleSave = useCallback(() => {
    const payload: {
      chart_ref: string
      chart_version: string
      values_schema_json?: object
      system_values_json?: object
    } = {
      chart_ref: chartRef.trim(),
      chart_version: chartVersion.trim(),
    }
    if (validSchema) payload.values_schema_json = validSchema
    if (validDefaults) payload.system_values_json = validDefaults
    onSave(payload)
  }, [chartRef, chartVersion, validSchema, validDefaults, onSave])

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Helm chart reference"
          placeholder="oci://registry/chart"
          value={chartRef}
          onChange={(e) => setChartRef(e.target.value)}
          fullWidth
        />
        <TextField
          label="Helm chart version"
          placeholder="1.0.0"
          value={chartVersion}
          onChange={(e) => setChartVersion(e.target.value)}
          sx={{ minWidth: 160 }}
        />
      </Stack>

      <SplitPane
        left={
          <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="body2" color="text.secondary">
                User values schema
              </Typography>
              {schemaValid ? (
                <CheckCircleIcon sx={{ fontSize: 18, color: 'success.main' }} />
              ) : (
                <ErrorIcon sx={{ fontSize: 18, color: 'error.main' }} />
              )}
            </Stack>
            <Box
              sx={{
                border: '1px solid rgba(148, 163, 184, 0.3)',
                borderRadius: 1,
                overflow: 'hidden',
                flex: 1,
              }}
            >
              <Editor
                height="100%"
                defaultLanguage="json"
                value={schemaText}
                onChange={handleSchemaChange}
                options={editorOptions}
                theme="vs-light"
              />
            </Box>
          </Box>
        }
        right={
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Deploy dialog preview
            </Typography>
            <Box
              sx={{
                border: '1px solid rgba(148, 163, 184, 0.3)',
                borderRadius: 1,
                p: 2,
              }}
            >
              <DeployDialogContent
                product={product}
                valuesSchemaJson={validSchema}
                initialValuesJson={null}
                onChange={() => {}}
              />
            </Box>
          </Box>
        }
      />

      <Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          System values
        </Typography>
        <Box sx={{ ...editorBoxSx, height: 150 }}>
          <Editor
            height="100%"
            defaultLanguage="json"
            value={defaultsText}
            onChange={handleDefaultsChange}
            options={editorOptions}
            theme="vs-light"
          />
        </Box>
      </Box>

      <Box>
        <Button
          variant="contained"
          disabled={!canSave}
          onClick={handleSave}
        >
          {saving ? 'Adding...' : 'Add template'}
        </Button>
      </Box>
    </Stack>
  )
}
