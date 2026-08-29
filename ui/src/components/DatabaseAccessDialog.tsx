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
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined'
import { DatabaseFields } from './DatabaseFields'
import { useDatabaseDetails } from './DatabasePanel'

interface DatabaseAccessDialogProps {
  userId: number
  deploymentId: string
  hostname: string | null | undefined
  onClose: () => void
}

/**
 * Focused modal showing a deployment's database details, opened from the
 * dashboard card's "Database" action. Reuses the same query as the availability
 * gate, so it opens instantly from cache, and keeps the password behind an
 * explicit reveal rather than on the persistent card surface.
 */
export function DatabaseAccessDialog({
  userId,
  deploymentId,
  hostname,
  onClose,
}: DatabaseAccessDialogProps) {
  const { data: database } = useDatabaseDetails(userId, deploymentId)

  return (
    // Wider than the SFTP dialog deliberately: a database and role name are
    // `dpl_` plus the deployment UUID's 32 hex digits, and the password is 48
    // more. At "xs" the value column is about 30 characters, so every one of
    // them wraps mid-identifier.
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <StorageOutlinedIcon color="primary" />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" noWrap>Database</Typography>
            {hostname && (
              <Typography variant="body2" color="text.secondary" noWrap>
                {hostname}
              </Typography>
            )}
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent>
        {database && <DatabaseFields database={database} />}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Done</Button>
      </DialogActions>
    </Dialog>
  )
}
