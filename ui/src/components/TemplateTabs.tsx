import { useEffect, useMemo, useState } from 'react'
import { Box, Tab, Tabs } from '@mui/material'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import StarIcon from '@mui/icons-material/Star'
import AddIcon from '@mui/icons-material/Add'
import { createTemplate, updateProductTemplate } from '../api/endpoints'
import type { Product, ProductTemplate } from '../api/types'
import { TemplateTabReadOnly } from './TemplateTabReadOnly'
import { TemplateTabNew } from './TemplateTabNew'

interface TemplateTabsProps {
  product: Product
  templates: ProductTemplate[]
  onError: (error: Error) => void
}

export function TemplateTabs({ product, templates, onError }: TemplateTabsProps) {
  const queryClient = useQueryClient()

  const sorted = useMemo(
    () =>
      [...templates].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      ),
    [templates],
  )

  const defaultTab = (tpls: typeof sorted): number | 'new' => {
    if (tpls.length === 0) return 'new'
    if (product.template_id && tpls.some((t) => t.id === product.template_id)) {
      return product.template_id
    }
    return tpls[tpls.length - 1].id
  }

  const [activeTab, setActiveTab] = useState<number | 'new'>(() => defaultTab(sorted))

  // Reset tab when templates change (e.g. product switch or first load)
  useEffect(() => {
    setActiveTab(defaultTab(sorted))
  }, [sorted, product.template_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const updateCanonicalMutation = useMutation({
    mutationFn: (templateId: number) =>
      updateProductTemplate(product.id, templateId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
    onError,
  })

  const createTemplateMutation = useMutation({
    mutationFn: (payload: {
      chart_ref: string
      chart_version: string
      values_schema_json?: object
      default_values_json?: object
    }) => createTemplate(product.id, payload),
    onSuccess: (template) => {
      queryClient.invalidateQueries({ queryKey: ['templates', product.id] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      if (!product.template_id) {
        updateCanonicalMutation.mutate(template.id)
      }
      setActiveTab(template.id)
    },
    onError,
  })

  const activeTemplate = sorted.find((t) => t.id === activeTab)

  return (
    <>
      <Tabs
        value={activeTab}
        onChange={(_, value) => setActiveTab(value)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        {sorted.map((template) => (
          <Tab
            key={template.id}
            value={template.id}
            icon={
              product.template_id === template.id ? (
                <StarIcon sx={{ fontSize: 16 }} />
              ) : undefined
            }
            iconPosition="start"
            label={`#${template.id}`}
            sx={{ minHeight: 48 }}
          />
        ))}
        <Tab
          value="new"
          icon={<AddIcon sx={{ fontSize: 16 }} />}
          iconPosition="start"
          label="New"
          sx={{ minHeight: 48, ml: 'auto' }}
        />
      </Tabs>
      <Box sx={{ p: 2 }}>
        {activeTab === 'new' ? (
          <TemplateTabNew
            product={product}
            templates={sorted}
            onSave={(payload) => createTemplateMutation.mutate(payload)}
            saving={createTemplateMutation.isPending}
          />
        ) : activeTemplate ? (
          <TemplateTabReadOnly
            product={product}
            template={activeTemplate}
            onMakeCanonical={(id) => updateCanonicalMutation.mutate(id)}
          />
        ) : null}
      </Box>
    </>
  )
}
