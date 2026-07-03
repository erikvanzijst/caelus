import { Box, Container, Stack, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { DISPLAY, fg, line, MONO, SANS } from './landing/landingTokens'
import { LEGAL_NAV } from '../content/legal'

interface AppFooterProps {
  /** Show the Admin link in the Navigate column. */
  isAdmin?: boolean
}

interface FooterLink {
  label: string
  to: string
}

const footerLinkSx = {
  fontFamily: SANS,
  fontSize: 14.5,
  color: fg.muted,
  transition: 'color 0.2s',
  '&:hover': { color: fg.primary },
}

/**
 * Footer for the authenticated app shell. Deliberately mirrors the anonymous
 * landing page's footer (brand block, mono column headers, small-print bar) so
 * the two surfaces read as one product — but its links are wired for the
 * signed-in context (in-app navigation + legal routes) rather than the landing
 * page's marketing anchors, which don't exist here.
 */
export function AppFooter({ isAdmin = false }: AppFooterProps) {
  const columns: { heading: string; links: FooterLink[] }[] = [
    {
      heading: 'Navigate',
      links: [
        { label: 'Dashboard', to: '/' },
        ...(isAdmin ? [{ label: 'Admin', to: '/admin' }] : []),
      ],
    },
    {
      heading: 'Legal',
      links: LEGAL_NAV.map((doc) => ({ label: doc.title, to: `/legal/${doc.slug}` })),
    },
  ]

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

          {/* Link columns */}
          <Stack direction="row" spacing={{ xs: 5, sm: 8 }} flexWrap="wrap" useFlexGap>
            {columns.map((col) => (
              <Stack key={col.heading} spacing={1.5}>
                <Typography
                  sx={{
                    fontFamily: MONO,
                    fontSize: 11.5,
                    letterSpacing: '0.16em',
                    textTransform: 'uppercase',
                    color: fg.faint,
                  }}
                >
                  {col.heading}
                </Typography>
                {col.links.map((link) => (
                  <Box key={link.label} component={RouterLink} to={link.to} sx={footerLinkSx}>
                    {link.label}
                  </Box>
                ))}
              </Stack>
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
