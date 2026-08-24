import { Alert, Button, CircularProgress } from '@mui/material'

interface PendingVarsNoticeProps {
  /** Whether head differs from what the running pod holds. */
  pending: boolean
  onApply: () => void
  applying?: boolean
  disabled?: boolean
}

/**
 * Tells the user that a configuration change is recorded but not running yet.
 *
 * Vars deliberately do not roll a deployment out on write — the CLI can stage
 * them, and a change made there is invisible here without this. The remedy is
 * a plain redeploy: the next release captures whatever the deployment's vars
 * currently are.
 *
 * Deliberately narrow: `pending` means "a rollout would change the pod's
 * environment", not staleness of any other kind, so this must not grow into a
 * general "something is out of date" banner.
 */
export function PendingVarsNotice({
  pending,
  onApply,
  applying,
  disabled,
}: PendingVarsNoticeProps) {
  if (!pending) {
    return null
  }

  return (
    <Alert
      severity="info"
      action={
        <Button
          size="small"
          color="inherit"
          onClick={onApply}
          disabled={applying || disabled}
          startIcon={applying ? <CircularProgress size={14} color="inherit" /> : undefined}
        >
          {applying ? 'Applying' : 'Apply now'}
        </Button>
      }
    >
      Configuration changes are saved but not running yet. Redeploy to apply them.
    </Alert>
  )
}
