import { Box, Dialog, DialogContent, DialogTitle, IconButton } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { LEGAL_DOCS } from '../content/legal'
import { LegalDocBody } from './LegalDocBody'

interface LegalDocModalProps {
  /** Slug into LEGAL_DOCS (e.g. "terms"). When undefined the modal is closed. */
  slug: string | null
  onClose: () => void
}

/**
 * Reads a legal document in a dialog stacked over whatever opened it (e.g. the
 * deploy dialog). The underlying dialog stays mounted, so closing this returns
 * the user to their form exactly as they left it. The document renders on a
 * light surface — LegalDocBody's typography is tuned for a white background.
 */
export function LegalDocModal({ slug, onClose }: LegalDocModalProps) {
  const doc = slug ? LEGAL_DOCS[slug] : undefined

  return (
    <Dialog open={Boolean(doc)} onClose={onClose} maxWidth="md" fullWidth scroll="paper">
      {doc && (
        <>
          <DialogTitle
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              bgcolor: '#fff',
              color: '#0d0f12',
              borderBottom: '1px solid #e5e7eb',
            }}
          >
            <Box component="span" sx={{ fontWeight: 700 }}>
              {doc.title}
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {/* Escape hatch: full page in a new tab (also enables printing). */}
              <IconButton
                component="a"
                href={`/legal/${doc.slug}`}
                target="_blank"
                rel="noopener noreferrer"
                size="small"
                aria-label={`Open ${doc.title} in a new tab`}
                sx={{ color: '#6b7280' }}
              >
                <OpenInNewIcon fontSize="small" />
              </IconButton>
              <IconButton onClick={onClose} size="small" aria-label="Close" sx={{ color: '#6b7280' }}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>
          </DialogTitle>
          <DialogContent dividers sx={{ bgcolor: '#fff', px: { xs: 2.5, md: 4 }, py: 3 }}>
            <LegalDocBody content={doc.content} />
          </DialogContent>
        </>
      )}
    </Dialog>
  )
}
