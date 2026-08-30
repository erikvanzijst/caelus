import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined'
import { SftpCredentialsFields } from './SftpCredentialsFields'
import { useSftpCredentials } from './SftpAccessPanel'

interface SftpAccessDialogProps {
  userId: number
  deploymentId: string
  hostname: string | null | undefined
  onClose: () => void
}

/**
 * Focused modal showing a deployment's SFTP connection details, opened from the
 * dashboard card's "Files" action. Reuses the same query as the availability
 * gate, so it opens instantly from cache.
 */
export function SftpAccessDialog({ userId, deploymentId, hostname, onClose }: SftpAccessDialogProps) {
  const { data: creds } = useSftpCredentials(userId, deploymentId)

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <FolderOutlinedIcon color="primary" />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" noWrap>File access</Typography>
            {hostname && (
              <Typography variant="body2" color="text.secondary" noWrap>
                {hostname}
              </Typography>
            )}
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Browse and download your app's files with any SFTP client (read-only).
        </Typography>
        {creds && <SftpCredentialsFields creds={creds} />}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Done</Button>
      </DialogActions>
    </Dialog>
  )
}
