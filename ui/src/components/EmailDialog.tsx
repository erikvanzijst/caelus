import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useState } from 'react'

interface EmailDialogProps {
  open: boolean
  onSave: (email: string) => void
  current?: string
}

function EmailDialog({ open, onSave, current }: EmailDialogProps) {
  const [value, setValue] = useState(current ?? '')

  return (
    <Dialog open={open} maxWidth="sm" fullWidth>
      <DialogTitle>Confirm your email</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">
            Authentication is handled upstream. For local use, confirm the email we should attach
            to requests.
          </Typography>
          <TextField
            autoFocus
            fullWidth
            label="Work email"
            placeholder="you@company.com"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button
          variant="contained"
          onClick={() => {
            const trimmed = value.trim()
            if (trimmed) onSave(trimmed)
          }}
        >
          Continue
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default EmailDialog
