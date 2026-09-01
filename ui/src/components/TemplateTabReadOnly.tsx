import { Box, Button, Stack, TextField, Typography } from '@mui/material'
import type { Product, ProductTemplate } from '../api/types'
import { formatDateTime } from '../utils/format'
import { LazyMonaco } from './LazyMonaco'
import { DeployDialogContent } from './DeployDialogContent'
import { SplitPane } from './SplitPane'

const editorBoxSx = {
  border: '1px solid rgba(148, 163, 184, 0.3)',
  borderRadius: 1,
  overflow: 'hidden',
  height: 150,
  resize: 'vertical' as const,
  minHeight: 100,
  maxHeight: 600,
  cursor: 'se-resize',
}

const editorOptions = {
  readOnly: true,
  minimap: { enabled: false },
  lineNumbers: 'on' as const,
  folding: false,
  wordWrap: 'off' as const,
  scrollBeyondLastLine: false,
  fontSize: 13,
  renderLineHighlight: 'none' as const,
  automaticLayout: true,
}

interface TemplateTabReadOnlyProps {
  product: Product
  template: ProductTemplate
  onMakeCanonical: (templateId: number) => void
}

export function TemplateTabReadOnly({
  product,
  template,
  onMakeCanonical,
}: TemplateTabReadOnlyProps) {
  const isCanonical = product.template_id === template.id

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Helm chart reference"
          value={template.chart_ref}
          slotProps={{ input: { readOnly: true } }}
          fullWidth
        />
        <TextField
          label="Helm chart version"
          value={template.chart_version}
          slotProps={{ input: { readOnly: true } }}
          sx={{ minWidth: 160 }}
        />
      </Stack>

      <SplitPane
        left={
          <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              User values schema
            </Typography>
            <Box
              sx={{
                border: '1px solid rgba(148, 163, 184, 0.3)',
                borderRadius: 1,
                overflow: 'hidden',
                flex: 1,
              }}
            >
              <LazyMonaco
                height="100%"
                defaultLanguage="json"
                value={
                  template.values_schema_json
                    ? JSON.stringify(template.values_schema_json, null, 2)
                    : ''
                }
                options={editorOptions}
                theme="vs-dark"
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
                valuesSchemaJson={
                  (template.values_schema_json as Record<string, unknown> | null) ?? null
                }
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
        <Box sx={editorBoxSx}>
          <LazyMonaco
            height="100%"
            defaultLanguage="json"
            value={
              template.system_values_json
                ? JSON.stringify(template.system_values_json, null, 2)
                : ''
            }
            options={editorOptions}
            theme="vs-dark"
          />
        </Box>
      </Box>

      {/* For a curated product the canonical pointer is catalog state: the
           reconciler repoints it to whichever template matches the file's spec,
           so offering the button here would only produce drift. */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 2,
          flexWrap: 'wrap',
        }}
      >
        {product.curated ? (
          <Typography variant="body2" color="text.secondary">
            {isCanonical
              ? 'Canonical — set by the catalog.'
              : 'Superseded. The canonical template is set by the catalog.'}
          </Typography>
        ) : (
          <Button
            variant="outlined"
            disabled={isCanonical}
            onClick={() => onMakeCanonical(template.id)}
          >
            {isCanonical ? 'Canonical' : 'Make canonical'}
          </Button>
        )}
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ marginLeft: 'auto', whiteSpace: 'nowrap' }}
        >
          Created {formatDateTime(template.created_at)}
        </Typography>
      </Box>
    </Stack>
  )
}
