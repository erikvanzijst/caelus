import { useState } from 'react'
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Tooltip,
} from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'

interface ConfirmDeleteDialogProps {
  name: string
  subject?: string
  confirmValue?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDeleteDialog({
  name,
  subject = 'item',
  confirmValue,
  onConfirm,
  onCancel,
}: ConfirmDeleteDialogProps) {
  const [confirmText, setConfirmText] = useState('')
  const [copied, setCopied] = useState(false)

  const canDelete = confirmValue ? confirmText === confirmValue : true

  function handleCopy() {
    navigator.clipboard.writeText(confirmValue!).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <Dialog open onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>Delete {subject}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          This will permanently delete the {subject} <strong>{name}</strong>.
          This action cannot be undone.
        </DialogContentText>
        {confirmValue && (
          <>
            <DialogContentText sx={{ mb: 2 }}>
              To confirm, type the hostname below:
            </DialogContentText>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <DialogContentText sx={{ fontFamily: 'monospace', fontWeight: 'bold' }}>
                {confirmValue}
              </DialogContentText>
              <Tooltip title={copied ? 'Copied!' : 'Copy hostname'}>
                <IconButton size="small" onClick={handleCopy}>
                  <ContentCopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
            <TextField
              autoFocus
              fullWidth
              size="small"
              placeholder={confirmValue}
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
            />
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button
          variant="contained"
          color="error"
          disabled={!canDelete}
          onClick={onConfirm}
        >
          Delete
        </Button>
      </DialogActions>
    </Dialog>
  )
}
