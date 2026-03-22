import { useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import DragIndicatorIcon from '@mui/icons-material/DragIndicator'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import Markdown from 'react-markdown'
import type { Plan } from '../api/types'

function formatPrice(priceCents: number, interval: string): string {
  const amount = (priceCents / 100).toFixed(priceCents % 100 === 0 ? 0 : 2)
  const suffix = interval === 'annual' ? '/yr' : '/mo'
  return priceCents === 0 ? 'Free' : `€${amount}${suffix}`
}

interface PlanCardProps {
  plan?: Plan
  selected?: boolean
  onSelect?: () => void
  onSave: (data: { name: string }) => void
  onCancel?: () => void
  onDelete?: () => void
  onEditingChange?: (editing: boolean) => void
  saving?: boolean
}

export function PlanCard({ plan, selected, onSelect, onSave, onCancel, onDelete, onEditingChange, saving }: PlanCardProps) {
  const isNew = !plan
  const [editing, setEditingRaw] = useState(isNew)

  function setEditing(value: boolean) {
    setEditingRaw(value)
    onEditingChange?.(value)
  }
  const [name, setName] = useState(plan?.name ?? '')

  const tmpl = plan?.template
  const price = tmpl ? formatPrice(tmpl.price_cents, tmpl.billing_interval) : null
  const description = tmpl?.description ?? null

  function handleSave() {
    const trimmedName = name.trim()
    if (!trimmedName) return
    onSave({ name: trimmedName })
    if (isNew) {
      setName('')
    } else {
      setEditing(false)
    }
  }

  function handleCancel() {
    if (isNew) {
      onCancel?.()
    } else {
      setName(plan.name)
      setEditing(false)
    }
  }

  return (
    <Card
      sx={{
        height: '100%',
        border: '2px solid',
        borderColor: selected ? 'primary.main' : 'transparent',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <CardContent
        sx={{ flex: 1, cursor: !editing ? 'pointer' : undefined }}
        onClick={!editing ? onSelect : undefined}
      >
        {editing ? (
          <Stack spacing={1.5}>
            <TextField
              label="Plan name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSave() }}
              size="small"
              autoFocus
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                size="small"
                onClick={handleSave}
                disabled={!name.trim() || saving}
              >
                {isNew ? 'Create' : 'Save'}
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={handleCancel}
              >
                Cancel
              </Button>
            </Stack>
          </Stack>
        ) : (
          <Stack spacing={1}>
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: -0.5, mb: -1 }}>
              <DragIndicatorIcon
                fontSize="small"
                sx={{ color: 'action.disabled', transform: 'rotate(90deg)', cursor: 'grab' }}
              />
            </Box>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
              <Typography variant="h6">{plan!.name}</Typography>
              <Stack direction="row" spacing={0.5}>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation()
                    setEditing(true)
                  }}
                >
                  <EditIcon fontSize="small" />
                </IconButton>
                {onDelete && (
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (window.confirm(`Delete plan "${plan!.name}"?`)) {
                        onDelete()
                      }
                    }}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                )}
              </Stack>
            </Stack>
            {tmpl ? (
              <>
                <Typography variant="h4" color="primary">
                  {price}
                </Typography>
                {description && (
                  <Box
                    sx={{
                      '& p': { m: 0, mb: 0.5 },
                      '& ul, & ol': { m: 0, pl: 2.5 },
                      '& li': { mb: 0.25 },
                      typography: 'body2',
                      color: 'text.secondary',
                    }}
                  >
                    <Markdown>{description}</Markdown>
                  </Box>
                )}
              </>
            ) : (
              <>
                <Skeleton variant="text" animation={false} width="60%" sx={{ fontSize: '2.125rem' }} />
                <Skeleton variant="text" animation={false} width="80%" />
                <Skeleton variant="text" animation={false} width="70%" />
                <Skeleton variant="text" animation={false} width="75%" />
              </>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
