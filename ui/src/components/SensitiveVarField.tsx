import { FormControl, FormHelperText, TextField } from '@mui/material'

interface SensitiveVarFieldProps {
  label: string
  description?: string
  required?: boolean
  error?: string
  readOnly?: boolean
  /** Whether the deployment already holds a value for this var. */
  alreadySet: boolean
  /** Whether the user has typed into this field during this session. */
  touched: boolean
  value: string
  onChange: (value: string) => void
}

/**
 * A write-only var: a password input that never displays a stored value.
 *
 * The platform cannot prefill it and deliberately does not try — a read of a
 * sensitive var omits its value entirely, so there is nothing to show and no
 * reveal control to offer. What the field has to communicate instead is that
 * leaving it alone is safe: an untouched field submits no value at all, and
 * the stored one is kept.
 *
 * The alternative, prefilling with a placeholder like `••••••`, invites the
 * user to submit the mask back as the new value, and an empty string would
 * wipe the secret outright.
 */
export function SensitiveVarField({
  label,
  description,
  required,
  error,
  readOnly,
  alreadySet,
  touched,
  value,
  onChange,
}: SensitiveVarFieldProps) {
  const unchanged = alreadySet && !touched
  const helper =
    error ??
    (unchanged
      ? description
        ? `${description} — currently set; leave blank to keep it.`
        : 'Currently set. Leave blank to keep it, or type a new value to replace it.'
      : description)

  return (
    <FormControl fullWidth error={!!error}>
      <TextField
        type="password"
        label={label}
        value={value}
        placeholder={unchanged ? 'unchanged' : undefined}
        onChange={(e) => onChange(e.target.value)}
        // Not `required` while a stored value exists: the field being empty
        // means "keep what is there", which satisfies the requirement.
        required={required && !alreadySet}
        error={!!error}
        autoComplete="new-password"
        helperText={helper}
        slotProps={readOnly ? { input: { readOnly: true } } : undefined}
      />
      {error && <FormHelperText>{error}</FormHelperText>}
    </FormControl>
  )
}
