import { Box, Typography } from '@mui/material'
import { accent, MONO } from './landing/landingTokens'

interface PageHeadingProps {
  /** Small mono label above the title, e.g. "YOUR SPACE". Rendered uppercase. */
  eyebrow: string
  title: string
  subtitle?: string
}

/**
 * Page-level header for the authenticated app (Dashboard, Admin). Mirrors the
 * landing page's eyebrow + heading rhythm — a Space Mono kicker over a sans
 * title — without adopting the landing's editorial serif, keeping in-app
 * surfaces utilitarian while still clearly part of the same brand.
 */
export function PageHeading({ eyebrow, title, subtitle }: PageHeadingProps) {
  return (
    <Box>
      <Typography
        variant="overline"
        sx={{
          display: 'block',
          color: accent.cyan,
          fontFamily: MONO,
          lineHeight: 1,
          mb: 1.25,
        }}
      >
        {eyebrow}
      </Typography>
      <Typography variant="h3">{title}</Typography>
      {subtitle && (
        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
          {subtitle}
        </Typography>
      )}
    </Box>
  )
}

export default PageHeading
