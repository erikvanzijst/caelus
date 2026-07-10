import { useState } from 'react'
import { Box, Divider, IconButton, Tooltip, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import CheckIcon from '@mui/icons-material/Check'
import { ApiError } from '../api/client'
import { getDeploymentSftp } from '../api/endpoints'

interface SftpAccessPanelProps {
  userId: number
  deploymentId: string
}

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

function CredentialRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 160 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontFamily: mono ? 'monospace' : undefined, flex: 1 }}>
        {value}
      </Typography>
      <CopyButton value={value} label={label.toLowerCase()} />
    </Box>
  )
}

/**
 * Read-only SFTP connection details for a deployment. Renders nothing when the
 * product exposes no files (the API returns 404), so page-level views can drop
 * it in unconditionally.
 */
export function SftpAccessPanel({ userId, deploymentId }: SftpAccessPanelProps) {
  const [revealed, setRevealed] = useState(false)

  const { data: creds, error } = useQuery({
    queryKey: ['deployment-sftp', userId, deploymentId],
    queryFn: () => getDeploymentSftp(userId, deploymentId),
    // 404 means "no file access for this product" — a normal state, don't retry.
    retry: (_count, err) => !(err instanceof ApiError && err.status === 404),
  })

  // Hide entirely when unavailable (404) or not yet loaded.
  if (error || !creds) return null

  const masked = '•'.repeat(Math.max(8, creds.password.length))

  return (
    <Box>
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle2" gutterBottom>
        File access (SFTP)
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Browse and download your app's files with any SFTP client. Access is
        read-only.
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <CredentialRow label="Host" value={creds.host} mono />
        <CredentialRow label="Port" value={String(creds.port)} mono />
        <CredentialRow label="Username" value={creds.username} mono />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" color="text.secondary" sx={{ minWidth: 160 }}>
            Password
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
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
    </Box>
  )
}
