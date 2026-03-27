import { useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  Stack,
  TextField,
} from '@mui/material'
import DragIndicatorIcon from '@mui/icons-material/DragIndicator'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import type { Plan } from '../api/types'
import { PlanCardContent } from './PlanCardContent'
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog'

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
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  function setEditing(value: boolean) {
    setEditingRaw(value)
    onEditingChange?.(value)
  }
  const [name, setName] = useState(plan?.name ?? '')

  const tmpl = plan?.template

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
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <PlanCardContent
                  name={plan!.name}
                  priceCents={tmpl?.price_cents}
                  billingInterval={tmpl?.billing_interval}
                  description={tmpl?.description}
                />
              </Box>
              <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
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
                  <>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation()
                        setConfirmingDelete(true)
                      }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                    {confirmingDelete && (
                      <ConfirmDeleteDialog
                        name={plan!.name}
                        subject="plan"
                        onConfirm={() => {
                          setConfirmingDelete(false)
                          onDelete()
                        }}
                        onCancel={() => setConfirmingDelete(false)}
                      />
                    )}
                  </>
                )}
              </Stack>
            </Stack>
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
