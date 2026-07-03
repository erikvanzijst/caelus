import { Box, Container, Stack, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { DISPLAY, fg, line, MONO, SANS } from './landing/landingTokens'
import { LEGAL_NAV } from '../content/legal'

const footerLinkSx = {
  fontFamily: SANS,
  fontSize: 14.5,
  color: fg.muted,
  transition: 'color 0.2s',
  '&:hover': { color: fg.primary },
}

/**
 * Footer for the authenticated app shell. Deliberately mirrors the anonymous
 * landing page's footer (brand block, mono column header, small-print bar) so
 * the two surfaces read as one product. Unlike the landing footer it carries no
 * "navigate" column: the signed-in app keeps its wayfinding in the sticky
 * header (the wordmark is home; Admin lives in the account menu), so the footer
 * is purpose-built for identity + legal — the links that genuinely belong here.
 */
export function AppFooter() {
  return (
    <Box
      component="footer"
      sx={{
        position: 'relative',
        zIndex: 1,
        borderTop: `1px solid ${line.soft}`,
        py: { xs: 6, md: 8 },
      }}
    >
      <Container maxWidth="xl">
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          spacing={{ xs: 5, md: 4 }}
        >
          {/* Brand block */}
          <Box sx={{ maxWidth: 320 }}>
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <Box component="img" src="/caelus.svg" alt="" sx={{ width: 28, height: 28 }} />
              <Typography
                sx={{
                  fontFamily: DISPLAY,
                  fontWeight: 600,
                  fontSize: 21,
                  color: fg.primary,
                  letterSpacing: '-0.02em',
                }}
              >
                Freepod
              </Typography>
            </Stack>
            <Typography
              sx={{ fontFamily: SANS, fontSize: 14.5, color: fg.muted, mt: 2, lineHeight: 1.6 }}
            >
              The European cloud that keeps your data yours. Private, open-source
              apps — free of ads, tracking and lock-in.
            </Typography>
          </Box>

          {/* Legal column */}
          <Stack spacing={1.5}>
            <Typography
              sx={{
                fontFamily: MONO,
                fontSize: 11.5,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                color: fg.faint,
              }}
            >
              Legal
            </Typography>
            {LEGAL_NAV.map((doc) => (
              <Box
                key={doc.slug}
                component={RouterLink}
                to={`/legal/${doc.slug}`}
                sx={footerLinkSx}
              >
                {doc.title}
              </Box>
            ))}
          </Stack>
        </Stack>

        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          spacing={1.5}
          sx={{ mt: { xs: 5, md: 7 }, pt: 3, borderTop: `1px solid ${line.softer}` }}
        >
          <Typography sx={{ fontFamily: SANS, fontSize: 13, color: fg.faint }}>
            © {new Date().getFullYear()} Freepod. All rights reserved.
          </Typography>
          <Typography sx={{ fontFamily: MONO, fontSize: 12, color: fg.faint, letterSpacing: '0.08em' }}>
            Hosted in the EU · Made for digital sovereignty
          </Typography>
        </Stack>
      </Container>
    </Box>
  )
}

export default AppFooter
