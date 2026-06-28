import { useState } from 'react'
import { TextField, Typography } from '@mui/material'
import type { TypographyProps } from '@mui/material'

interface InlineEditFieldProps {
  /** The current persisted value. */
  value?: string | null
  /** Text shown when there is no value; also used as the input placeholder. */
  emptyText: string
  /**
   * Persist the new value (null when cleared). Called only when the trimmed
   * value actually changed.
   */
  onSave: (next: string | null) => void
  multiline?: boolean
  /** Extra props/styling for the read-only display Typography. */
  typographyProps?: TypographyProps
}

/**
 * Click-to-edit text field: renders the value as Typography and swaps to a
 * standard TextField on click, saving on blur or Enter (Escape cancels).
 */
export function InlineEditField({
  value,
  emptyText,
  onSave,
  multiline = false,
  typographyProps,
}: InlineEditFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  function save() {
    const trimmed = draft.trim()
    if (trimmed !== (value ?? '')) {
      onSave(trimmed || null)
    }
    setEditing(false)
  }

  if (editing) {
    return (
      <TextField
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (!multiline || !e.shiftKey)) save()
          if (e.key === 'Escape') setEditing(false)
        }}
        variant="standard"
        autoFocus
        multiline={multiline}
        placeholder={emptyText}
      />
    )
  }

  return (
    <Typography
      color="text.secondary"
      onClick={() => {
        setDraft(value ?? '')
        setEditing(true)
      }}
      sx={{ cursor: 'pointer', '&:hover': { color: 'primary.main' } }}
      {...typographyProps}
    >
      {value || emptyText}
    </Typography>
  )
}
