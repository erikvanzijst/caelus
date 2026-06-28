import { Box, Container, Stack, Typography } from '@mui/material'
import { accent, DISPLAY, fg, line, MONO, SANS } from './landingTokens'
import Reveal from './Reveal'

const contrasts = [
  {
    them: 'You are the product. Your data is often harvested, profiled and sold to advertisers and brokers.',
    us: 'You are the customer. You pay a fair price; we never monetise your data.',
  },
  {
    them: 'Your data is held hostage — deliberately hard to export so you can’t leave.',
    us: 'Open formats and standard tools. Export everything and walk away whenever you want.',
  },
  {
    them: 'Hosted under US, Chinese or other foreign jurisdiction, within reach of foreign governments.',
    us: 'Hosted in Europe, on open-source software, under European privacy law.',
  },
]

/** The "why we exist" manifesto: the Big Tech bargain vs. the Freepod bargain. */
export function MissionSection() {
  return (
    <Box component="section" sx={{ py: { xs: 9, md: 14 } }}>
      <Container maxWidth="lg">
        <Reveal>
          <Typography
            sx={{
              fontFamily: MONO,
              fontSize: 12.5,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: accent.magenta,
              mb: 3,
            }}
          >
            Why Freepod exists
          </Typography>
          <Typography
            component="h2"
            sx={{
              fontFamily: DISPLAY,
              fontWeight: 500,
              color: fg.primary,
              fontSize: { xs: 30, md: 44 },
              lineHeight: 1.12,
              letterSpacing: '-0.02em',
              maxWidth: 880,
            }}
          >
            The big platforms gave us convenience — and quietly took our
            privacy, our choices, and our data in return.
          </Typography>
        </Reveal>

        <Stack spacing={2.5} sx={{ mt: { xs: 6, md: 8 } }}>
          {/* Column labels */}
          <Stack
            direction="row"
            sx={{ display: { xs: 'none', md: 'flex' }, px: 1 }}
          >
            <Typography
              sx={{
                flex: 1,
                fontFamily: MONO,
                fontSize: 12,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: fg.faint,
              }}
            >
              Big Tech
            </Typography>
            <Typography
              sx={{
                flex: 1,
                fontFamily: MONO,
                fontSize: 12,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: accent.cyan,
                pl: 4,
              }}
            >
              The Freepod way
            </Typography>
          </Stack>

          {contrasts.map((row, i) => (
            <Reveal key={i} delay={i * 90}>
              <Stack
                direction={{ xs: 'column', md: 'row' }}
                sx={{
                  borderTop: `1px solid ${line.soft}`,
                  pt: 3,
                  gap: { xs: 2, md: 0 },
                }}
              >
                <Typography
                  sx={{
                    flex: 1,
                    fontFamily: SANS,
                    fontSize: { xs: 16, md: 18 },
                    lineHeight: 1.55,
                    color: fg.faint,
                    pr: { md: 4 },
                  }}
                >
                  {row.them}
                </Typography>
                <Box
                  sx={{
                    flex: 1,
                    pl: { md: 4 },
                    borderLeft: { md: `1px solid ${line.soft}` },
                  }}
                >
                  <Typography
                    sx={{
                      fontFamily: SANS,
                      fontSize: { xs: 16, md: 18 },
                      lineHeight: 1.55,
                      color: fg.primary,
                    }}
                  >
                    {row.us}
                  </Typography>
                </Box>
              </Stack>
            </Reveal>
          ))}
        </Stack>
      </Container>
    </Box>
  )
}

export default MissionSection
