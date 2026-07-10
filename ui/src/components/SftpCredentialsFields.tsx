import { useState } from 'react'
import { Box, IconButton, Tooltip, Typography } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import CheckIcon from '@mui/icons-material/Check'
import type { SftpCredentials } from '../api/types'

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Tooltip title={copied ? 'Copied' : `Copy ${label}`}>
      <IconButton
        size="small"
        aria-label={`Copy ${label}`}
        onClick={() => {
          void navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
      >
        {copied ? <CheckIcon fontSize="inherit" /> : <ContentCopyIcon fontSize="inherit" />}
      </IconButton>
    </Tooltip>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 96 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
        {value}
      </Typography>
      <CopyButton value={value} label={label.toLowerCase()} />
    </Box>
  )
}

/**
 * Presentational SFTP connection fields (host/port/username + revealable,
 * copyable password). Pure — takes resolved credentials. Shared by the inline
 * SftpAccessPanel (admin deployment dialog) and the SftpAccessDialog (user
 * dashboard card) so the two surfaces can never drift.
 */
export function SftpCredentialsFields({ creds }: { creds: SftpCredentials }) {
  const [revealed, setRevealed] = useState(false)
  const masked = '•'.repeat(Math.max(8, creds.password.length))

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      <Row label="Host" value={creds.host} />
      <Row label="Port" value={String(creds.port)} />
      <Row label="Username" value={creds.username} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 96 }}>
          Password
        </Typography>
        <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
          {revealed ? creds.password : masked}
        </Typography>
        <Tooltip title={revealed ? 'Hide password' : 'Show password'}>
          <IconButton
            size="small"
            aria-label={revealed ? 'Hide password' : 'Show password'}
            onClick={() => setRevealed((v) => !v)}
          >
            {revealed ? <VisibilityOffIcon fontSize="inherit" /> : <VisibilityIcon fontSize="inherit" />}
          </IconButton>
        </Tooltip>
        <CopyButton value={creds.password} label="password" />
      </Box>
    </Box>
  )
}
