import { Box, Button, Container, Stack, Typography } from '@mui/material'
import { DISPLAY, fg, line } from './landingTokens'

interface LandingNavProps {
  onSignup: () => void
}

const navLinks = [
  { label: 'Apps', href: '#apps' },
  { label: 'Why Freepod', href: '#why' },
  { label: 'Pricing', href: '#pricing' },
]

/** Sticky, translucent top navigation for the landing page. */
export function LandingNav({ onSignup }: LandingNavProps) {
  return (
    <Box
      component="header"
      sx={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        borderBottom: `1px solid ${line.softer}`,
        background: 'rgba(7, 10, 20, 0.62)',
        backdropFilter: 'blur(14px)',
      }}
    >
      <Container maxWidth="lg">
        <Stack
          direction="row"
          alignItems="center"
          sx={{ height: 72, gap: 2 }}
        >
          {/* Brand */}
          <Stack direction="row" alignItems="center" spacing={1.25}>
            <Box
              component="img"
              src="/caelus.svg"
              alt=""
              sx={{ width: 30, height: 30 }}
            />
            <Typography
              sx={{
                fontFamily: DISPLAY,
                fontWeight: 600,
                fontSize: 22,
                letterSpacing: '-0.02em',
                color: fg.primary,
              }}
            >
              Freepod
            </Typography>
          </Stack>

          <Box sx={{ flex: 1 }} />

          {/* Section links — hidden on small screens */}
          <Stack
            direction="row"
            spacing={3.5}
            sx={{ display: { xs: 'none', md: 'flex' }, mr: 1 }}
          >
            {navLinks.map((link) => (
              <Box
                key={link.href}
                component="a"
                href={link.href}
                sx={{
                  fontSize: 15,
                  color: fg.muted,
                  transition: 'color 0.2s',
                  '&:hover': { color: fg.primary },
                }}
              >
                {link.label}
              </Box>
            ))}
          </Stack>

          <Button
            onClick={onSignup}
            sx={{
              color: fg.muted,
              fontSize: 15,
              px: 1.5,
              '&:hover': { color: fg.primary, background: 'transparent' },
            }}
          >
            Log in
          </Button>
          <Button
            variant="contained"
            onClick={onSignup}
            sx={{
              borderRadius: 999,
              px: 2.5,
              fontWeight: 600,
              color: '#fff',
              background: 'linear-gradient(120deg, #2563EB, #6D5BFF)',
              boxShadow: '0 8px 24px rgba(37,99,235,0.35)',
              '&:hover': {
                background: 'linear-gradient(120deg, #1d4fd0, #5d4bf0)',
              },
            }}
          >
            Create account
          </Button>
        </Stack>
      </Container>
    </Box>
  )
}

export default LandingNav
