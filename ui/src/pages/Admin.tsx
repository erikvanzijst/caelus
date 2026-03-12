import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Collapse,
  Divider,
  Grid,
  IconButton,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import Editor from '@monaco-editor/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  createTemplate,
  deleteTemplate,
  listProducts,
  listTemplates,
  updateProductTemplate,
} from '../api/endpoints'
import type { Product } from '../api/types'
import { useAuth } from '../state/AuthContext'
import { formatDateTime } from '../utils/format'
import { NewProduct } from '../components/NewProduct'
import { ProductList } from '../components/ProductList'
import { SelectedProduct } from '../components/SelectedProduct'

const DEFAULT_VALUES_SCHEMA = `{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
  },
  "additionalProperties": false
}`

function Admin() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null)
  const [templateChartRef, setTemplateChartRef] = useState('')
  const [templateChartVersion, setTemplateChartVersion] = useState('')
  const [valuesSchemaJson, setValuesSchemaJson] = useState(DEFAULT_VALUES_SCHEMA)
  const [schemaError, setSchemaError] = useState<string | null>(null)
  const [defaultValuesJson, setDefaultValuesJson] = useState('')
  const [defaultValuesError, setDefaultValuesError] = useState<string | null>(null)
  const [expandedSchemaId, setExpandedSchemaId] = useState<number | null>(null)
  const [expandedDefaultsId, setExpandedDefaultsId] = useState<number | null>(null)
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
    return productsQuery.data?.find((product) => product.id === selectedProductId)
  }, [productsQuery.data, selectedProductId])

  const templatesQuery = useQuery({
    queryKey: ['templates', selectedProductId],
    queryFn: () => listTemplates(selectedProductId!),
    enabled: Boolean(selectedProductId),
  })

  const canonicalTemplate = useMemo(() => {
    if (!selectedProduct?.template_id || !templatesQuery.data) return undefined
    return templatesQuery.data.find((t) => t.id === selectedProduct.template_id)
  }, [selectedProduct?.template_id, templatesQuery.data])

  // Prefill form fields from canonical template when switching products
  useEffect(() => {
    if (canonicalTemplate) {
      setTemplateChartRef(canonicalTemplate.chart_ref)
      setTemplateChartVersion('')
      setDefaultValuesJson(
        canonicalTemplate.default_values_json
          ? JSON.stringify(canonicalTemplate.default_values_json, null, 2)
          : '',
      )
      setValuesSchemaJson(
        canonicalTemplate.values_schema_json
          ? JSON.stringify(canonicalTemplate.values_schema_json, null, 2)
          : DEFAULT_VALUES_SCHEMA,
      )
    } else {
      setTemplateChartRef('')
      setTemplateChartVersion('')
      setDefaultValuesJson('')
      setValuesSchemaJson(DEFAULT_VALUES_SCHEMA)
    }
  }, [canonicalTemplate])

  const createTemplateMutation = useMutation({
    mutationFn: () => {
      let parsedSchema: object | undefined
      if (valuesSchemaJson.trim()) {
        try {
          parsedSchema = JSON.parse(valuesSchemaJson)
          setSchemaError(null)
        } catch {
          setSchemaError('Invalid JSON in values schema')
          throw new Error('Invalid JSON in values schema')
        }
      }
      let parsedDefaults: object | undefined
      if (defaultValuesJson.trim()) {
        try {
          parsedDefaults = JSON.parse(defaultValuesJson)
          setDefaultValuesError(null)
        } catch {
          setDefaultValuesError('Invalid JSON in default values')
          throw new Error('Invalid JSON in default values')
        }
      }
      return createTemplate(
        selectedProductId!,
        {
          chart_ref: templateChartRef.trim(),
          chart_version: templateChartVersion.trim(),
          values_schema_json: parsedSchema,
          default_values_json: parsedDefaults,
        },
      )
    },
    onSuccess: (template) => {
      setTemplateChartVersion('')
      queryClient.invalidateQueries({ queryKey: ['templates', selectedProductId] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      if (!selectedProduct?.template_id) {
        updateCanonicalMutation.mutate(template.id)
      }
    },
    onError: (error: Error) => setAdminError(error.message),
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (payload: { templateId: number; wasCanonical: boolean }) =>
      deleteTemplate(selectedProductId!, payload.templateId).then(() => payload),
    onSuccess: async (payload) => {
      queryClient.invalidateQueries({ queryKey: ['templates', selectedProductId] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      if (!payload.wasCanonical) return
      const templates = await queryClient.fetchQuery({
        queryKey: ['templates', selectedProductId],
        queryFn: () => listTemplates(selectedProductId!),
      })
      const newest = [...templates].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )[0]
      if (newest) {
        updateCanonicalMutation.mutate(newest.id)
      }
    },
  })

  const updateCanonicalMutation = useMutation({
    mutationFn: (templateId: number) =>
      updateProductTemplate(selectedProductId!, templateId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
    onError: (error: Error) => setAdminError(error.message),
  })

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h3">Admin</Typography>
        <Typography color="text.secondary">
          Manage products, template versions, and the canonical template selection.
        </Typography>
      </Box>
      {adminError && <Alert severity="error">{adminError}</Alert>}
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Stack spacing={2}>
            <NewProduct
              onSuccess={() => queryClient.invalidateQueries({ queryKey: ['products'] })}
              onError={(error: Error) => setAdminError(error.message)}
            />
            <ProductList
              products={productsQuery.data}
              selectedProductId={selectedProductId}
              onSelectProduct={setSelectedProductId}
            />
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Stack spacing={2}>
            <SelectedProduct
              key={selectedProductId}
              product={selectedProduct}
              onError={(error: Error) => setAdminError(error.message)}
            />

            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Create product template</Typography>
                  <TextField
                    label="Helm chart reference"
                    placeholder="ghcr.io/org/chart"
                    value={templateChartRef}
                    onChange={(event) => setTemplateChartRef(event.target.value)}
                    disabled={!selectedProductId}
                  />
                  <TextField
                    label="Helm chart tag"
                    placeholder="1.0.0"
                    value={templateChartVersion}
                    onChange={(event) => setTemplateChartVersion(event.target.value)}
                    disabled={!selectedProductId}
                  />
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Default Helm values (JSON -- optional)
                    </Typography>
                    <Box
                      sx={{
                        border: '1px solid rgba(148, 163, 184, 0.3)',
                        borderRadius: 1,
                        overflow: 'hidden',
                        resize: 'vertical',
                        minHeight: 100,
                        maxHeight: 600,
                        cursor: 'se-resize',
                        height: 150,
                      }}
                    >
                      <Editor
                        height="100%"
                        defaultLanguage="json"
                        value={defaultValuesJson}
                        onChange={(value) => {
                          setDefaultValuesJson(value || '')
                          setDefaultValuesError(null)
                        }}
                        options={{
                          minimap: { enabled: false },
                          lineNumbers: 'on',
                          folding: false,
                          wordWrap: 'on',
                          scrollBeyondLastLine: false,
                          fontSize: 13,
                          renderLineHighlight: 'none',
                          automaticLayout: true,
                        }}
                        theme="vs-light"
                      />
                    </Box>
                    {defaultValuesError && (
                      <Typography variant="body2" color="error" sx={{ mt: 0.5 }}>
                        {defaultValuesError}
                      </Typography>
                    )}
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Helm chart user values schema
                    </Typography>
                    <Box
                      sx={{
                        border: '1px solid rgba(148, 163, 184, 0.3)',
                        borderRadius: 1,
                        overflow: 'hidden',
                        resize: 'vertical',
                        minHeight: 100,
                        maxHeight: 600,
                        cursor: 'se-resize',
                        height: 150,
                      }}
                    >
                      <Editor
                        height="100%"
                        defaultLanguage="json"
                        value={valuesSchemaJson}
                        onChange={(value) => {
                          setValuesSchemaJson(value || '')
                          setSchemaError(null)
                        }}
                        options={{
                          minimap: { enabled: false },
                          lineNumbers: 'on',
                          folding: false,
                          wordWrap: 'on',
                          scrollBeyondLastLine: false,
                          fontSize: 13,
                          renderLineHighlight: 'none',
                          automaticLayout: true,
                        }}
                        theme="vs-light"
                      />
                    </Box>
                    {schemaError && (
                      <Typography variant="body2" color="error" sx={{ mt: 0.5 }}>
                        {schemaError}
                      </Typography>
                    )}
                  </Box>
                </Stack>
              </CardContent>
              <CardActions sx={{ px: 2, pb: 2 }}>
                <Button
                  variant="contained"
                  disabled={
                    !selectedProductId ||
                    !templateChartRef.trim() ||
                    !templateChartVersion.trim() ||
                    createTemplateMutation.isPending
                  }
                  onClick={() => {
                    setAdminError(null)
                    createTemplateMutation.mutate()
                  }}
                >
                  Add template
                </Button>
              </CardActions>
            </Card>

            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Product template versions</Typography>
                  <Divider />
                  {templatesQuery.data?.map((template) => (
                    <Box
                      key={template.id}
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        border: '1px solid rgba(148, 163, 184, 0.2)',
                      }}
                    >
                      <Stack spacing={1}>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Typography variant="subtitle1">Template #{template.id}</Typography>
                          {selectedProduct?.template_id === template.id && (
                            <Chip label="Canonical" color="primary" size="small" />
                          )}
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                          {template.chart_ref}:{template.chart_version}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Created {formatDateTime(template.created_at)}
                        </Typography>
                        {template.default_values_json && (
                          <>
                            <Box>
                              <IconButton
                                size="small"
                                onClick={() =>
                                  setExpandedDefaultsId(
                                    expandedDefaultsId === template.id ? null : template.id,
                                  )
                                }
                              >
                                <ExpandMore
                                  sx={{
                                    transform:
                                      expandedDefaultsId === template.id
                                        ? 'rotate(180deg)'
                                        : 'rotate(0deg)',
                                    transition: 'transform 0.2s',
                                  }}
                                />
                              </IconButton>
                              <Typography variant="body2" component="span">
                                Default Helm values
                              </Typography>
                            </Box>
                            <Collapse in={expandedDefaultsId === template.id}>
                              <Box
                                sx={{
                                  border: '1px solid rgba(148, 163, 184, 0.3)',
                                  borderRadius: 1,
                                  overflow: 'hidden',
                                  resize: 'vertical',
                                  minHeight: 100,
                                  maxHeight: 600,
                                  cursor: 'se-resize',
                                  height: 150,
                                }}
                              >
                                <Editor
                                  height="100%"
                                  defaultLanguage="json"
                                  value={JSON.stringify(template.default_values_json, null, 2)}
                                  options={{
                                    readOnly: true,
                                    minimap: { enabled: false },
                                    lineNumbers: 'on',
                                    folding: false,
                                    wordWrap: 'on',
                                    scrollBeyondLastLine: false,
                                    fontSize: 13,
                                    renderLineHighlight: 'none',
                                    automaticLayout: true,
                                  }}
                                  theme="vs-light"
                                />
                              </Box>
                            </Collapse>
                          </>
                        )}
                        {template.values_schema_json && (
                          <>
                            <Box>
                              <IconButton
                                size="small"
                                onClick={() =>
                                  setExpandedSchemaId(
                                    expandedSchemaId === template.id ? null : template.id,
                                  )
                                }
                              >
                                <ExpandMore
                                  sx={{
                                    transform:
                                      expandedSchemaId === template.id
                                        ? 'rotate(180deg)'
                                        : 'rotate(0deg)',
                                    transition: 'transform 0.2s',
                                  }}
                                />
                              </IconButton>
                              <Typography variant="body2" component="span">
                                Helm chart user values schema
                              </Typography>
                            </Box>
                            <Collapse in={expandedSchemaId === template.id}>
                              <Box
                                sx={{
                                  border: '1px solid rgba(148, 163, 184, 0.3)',
                                  borderRadius: 1,
                                  overflow: 'hidden',
                                  resize: 'vertical',
                                  minHeight: 100,
                                  maxHeight: 600,
                                  cursor: 'se-resize',
                                  height: 150,
                                }}
                              >
                                <Editor
                                  height="100%"
                                  defaultLanguage="json"
                                  value={JSON.stringify(template.values_schema_json, null, 2)}
                                  options={{
                                    readOnly: true,
                                    minimap: { enabled: false },
                                    lineNumbers: 'on',
                                    folding: false,
                                    wordWrap: 'on',
                                    scrollBeyondLastLine: false,
                                    fontSize: 13,
                                    renderLineHighlight: 'none',
                                    automaticLayout: true,
                                  }}
                                  theme="vs-light"
                                />
                              </Box>
                            </Collapse>
                          </>
                        )}
                        <Stack direction="row" spacing={1}>
                          <Button
                            variant="outlined"
                            onClick={() => updateCanonicalMutation.mutate(template.id)}
                          >
                            Set canonical
                          </Button>
                          <Button
                            variant="outlined"
                            color="secondary"
                            onClick={() => {
                              if (window.confirm('Delete this template version?')) {
                                setAdminError(null)
                                deleteTemplateMutation.mutate({
                                  templateId: template.id,
                                  wasCanonical: selectedProduct?.template_id === template.id,
                                })
                              }
                            }}
                          >
                            Delete
                          </Button>
                        </Stack>
                      </Stack>
                    </Box>
                  ))}
                  {!templatesQuery.isLoading && templatesQuery.data?.length === 0 && (
                    <Typography color="text.secondary">
                      No templates yet. Add the first version to unlock deployments.
                    </Typography>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  )
}

export default Admin
