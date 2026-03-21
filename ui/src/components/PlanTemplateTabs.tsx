import { useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import StarIcon from '@mui/icons-material/Star'
import AddIcon from '@mui/icons-material/Add'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createPlanTemplate, updatePlan } from '../api/endpoints'
import type { Plan, PlanTemplateVersion } from '../api/types'

function formatPrice(cents: number): string {
  return cents === 0 ? 'Free' : `€${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`
}

function formatStorage(bytes: number | null | undefined): string {
  if (!bytes) return 'None'
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(1)} TB`
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  return `${bytes} B`
}

interface PlanTemplateTabsProps {
  plan: Plan
  templates: PlanTemplateVersion[]
  onError: (error: Error) => void
}

export function PlanTemplateTabs({ plan, templates, onError }: PlanTemplateTabsProps) {
  const queryClient = useQueryClient()

  const sorted = useMemo(
    () => [...templates].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [templates],
  )

  const defaultTab = (tpls: typeof sorted): number | 'new' => {
    if (tpls.length === 0) return 'new'
    if (plan.template_id && tpls.some((t) => t.id === plan.template_id)) {
      return plan.template_id
    }
    return tpls[tpls.length - 1].id
  }

  const [activeTab, setActiveTab] = useState<number | 'new'>(() => defaultTab(sorted))

  useEffect(() => {
    setActiveTab(defaultTab(sorted))
  }, [sorted, plan.template_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const makeCanonicalMutation = useMutation({
    mutationFn: (templateId: number) => updatePlan(plan.id, { template_id: templateId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
    },
    onError,
  })

  const createMutation = useMutation({
    mutationFn: (payload: { price_cents: number; billing_interval: string; storage_bytes?: number | null }) =>
      createPlanTemplate(plan.id, payload),
    onSuccess: (tmpl) => {
      queryClient.invalidateQueries({ queryKey: ['plan-templates', plan.id] })
      // Auto-set as canonical if this is the first template
      if (!plan.template_id) {
        makeCanonicalMutation.mutate(tmpl.id)
      }
      setActiveTab(tmpl.id)
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
        {sorted.map((tmpl) => (
          <Tab
            key={tmpl.id}
            value={tmpl.id}
            icon={plan.template_id === tmpl.id ? <StarIcon sx={{ fontSize: 16 }} /> : undefined}
            iconPosition="start"
            label={`#${tmpl.id}`}
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
          <NewPlanTemplateForm
            onSave={(payload) => createMutation.mutate(payload)}
            saving={createMutation.isPending}
          />
        ) : activeTemplate ? (
          <PlanTemplateReadOnly
            template={activeTemplate}
            isCanonical={plan.template_id === activeTemplate.id}
            onMakeCanonical={() => makeCanonicalMutation.mutate(activeTemplate.id)}
          />
        ) : null}
      </Box>
    </>
  )
}

// ---------------------------------------------------------------------------
// Read-only view for an existing plan template version
// ---------------------------------------------------------------------------

interface PlanTemplateReadOnlyProps {
  template: PlanTemplateVersion
  isCanonical: boolean
  onMakeCanonical: () => void
}

function PlanTemplateReadOnly({ template, isCanonical, onMakeCanonical }: PlanTemplateReadOnlyProps) {
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={4}>
        <Box>
          <Typography variant="caption" color="text.secondary">Price</Typography>
          <Typography variant="h6">{formatPrice(template.price_cents)}</Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">Billing interval</Typography>
          <Typography variant="h6" sx={{ textTransform: 'capitalize' }}>{template.billing_interval}</Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">Storage</Typography>
          <Typography variant="h6">{formatStorage(template.storage_bytes)}</Typography>
        </Box>
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Created {new Date(template.created_at).toLocaleString()}
      </Typography>
      {isCanonical ? (
        <Button variant="outlined" disabled startIcon={<StarIcon />}>
          Canonical
        </Button>
      ) : (
        <Button variant="outlined" onClick={onMakeCanonical} startIcon={<StarIcon />}>
          Make canonical
        </Button>
      )}
    </Stack>
  )
}

// ---------------------------------------------------------------------------
// Form for creating a new plan template version
// ---------------------------------------------------------------------------

interface NewPlanTemplateFormProps {
  onSave: (payload: { price_cents: number; billing_interval: string; storage_bytes?: number | null }) => void
  saving: boolean
}

function NewPlanTemplateForm({ onSave, saving }: NewPlanTemplateFormProps) {
  const [priceCents, setPriceCents] = useState('')
  const [billingInterval, setBillingInterval] = useState('monthly')
  const [storageGb, setStorageGb] = useState('')

  function handleSubmit() {
    const cents = Math.round(parseFloat(priceCents) * 100)
    if (isNaN(cents) || cents < 0) return
    const storageBytes = storageGb ? Math.round(parseFloat(storageGb) * 1024 ** 3) : null
    onSave({
      price_cents: cents,
      billing_interval: billingInterval,
      storage_bytes: storageBytes,
    })
    setPriceCents('')
    setStorageGb('')
  }

  const valid = priceCents !== '' && !isNaN(parseFloat(priceCents)) && parseFloat(priceCents) >= 0

  return (
    <Stack spacing={2} sx={{ maxWidth: 400 }}>
      <TextField
        label="Price (€)"
        value={priceCents}
        onChange={(e) => setPriceCents(e.target.value)}
        type="number"
        size="small"
        autoFocus
        helperText="Enter 0 for a free plan"
        slotProps={{ htmlInput: { min: 0, step: 0.01 } }}
      />
      <TextField
        label="Billing interval"
        value={billingInterval}
        onChange={(e) => setBillingInterval(e.target.value)}
        size="small"
        select
      >
        <MenuItem value="monthly">Monthly</MenuItem>
        <MenuItem value="annual">Annual</MenuItem>
      </TextField>
      <TextField
        label="Storage (GB)"
        value={storageGb}
        onChange={(e) => setStorageGb(e.target.value)}
        type="number"
        size="small"
        helperText="Leave empty for no storage limit"
        slotProps={{ htmlInput: { min: 0 } }}
      />
      <Button
        variant="contained"
        onClick={handleSubmit}
        disabled={!valid || saving}
      >
        Create template
      </Button>
    </Stack>
  )
}
