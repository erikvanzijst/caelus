import { useState } from 'react'
import { Checkbox, FormControlLabel, Link, Typography } from '@mui/material'
import { LegalDocModal } from './LegalDocModal'

interface TosAgreementProps {
  checked: boolean
  onChange: (checked: boolean) => void
}

/**
 * Required agreement control for the deploy dialog: a checkbox whose label links
 * the legal documents. Only the Terms of Service is actively accepted; the
 * Acceptable Use Policy is incorporated by reference and the Privacy Policy is
 * acknowledged. Each link opens the document in a nested modal so the user never
 * leaves the deploy form. The accepted ToS version is owned by the parent — this
 * component only captures the checkbox state.
 */
export function TosAgreement({ checked, onChange }: TosAgreementProps) {
  const [openSlug, setOpenSlug] = useState<string | null>(null)

  // Render as a button so the link is keyboard-focusable and does not submit or
  // toggle the surrounding checkbox when activated.
  const docLink = (slug: string, label: string) => (
    <Link
      component="button"
      type="button"
      underline="hover"
      onClick={(e) => {
        e.preventDefault()
        setOpenSlug(slug)
      }}
      sx={{ verticalAlign: 'baseline' }}
    >
      {label}
    </Link>
  )

  return (
    <>
      <FormControlLabel
        control={
          <Checkbox
            checked={checked}
            onChange={(e) => onChange(e.target.checked)}
            sx={{ alignSelf: 'flex-start', pt: 0.25 }}
          />
        }
        label={
          <Typography variant="body2" color="text.secondary">
            I agree to the Freepod {docLink('terms', 'Terms of Service')} and{' '}
            {docLink('aup', 'Acceptable Use Policy')}, and acknowledge the{' '}
            {docLink('privacy', 'Privacy Policy')}.
          </Typography>
        }
        sx={{ alignItems: 'flex-start', m: 0 }}
      />
      <LegalDocModal slug={openSlug} onClose={() => setOpenSlug(null)} />
    </>
  )
}
