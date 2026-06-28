import { Box, Button, Container, Stack, Typography } from '@mui/material'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import { DISPLAY, fg, line, SANS } from './landingTokens'
import AuroraBackground from './AuroraBackground'
import Reveal from './Reveal'

interface CtaBandProps {
  onSignup: () => void
}

/** Final, high-contrast conversion band before the footer. */
export function CtaBand({ onSignup }: CtaBandProps) {
  return (
    <Box component="section" sx={{ px: { xs: 2, md: 3 }, py: { xs: 4, md: 8 } }}>
      <Container maxWidth="lg" disableGutters>
        <Reveal>
          <Box
            sx={{
              position: 'relative',
              overflow: 'hidden',
              borderRadius: 6,
              border: `1px solid ${line.soft}`,
              px: { xs: 4, md: 10 },
              py: { xs: 8, md: 12 },
              textAlign: 'center',
            }}
          >
            <AuroraBackground subtle />
            <Box sx={{ position: 'relative', zIndex: 1 }}>
              <Typography
                component="h2"
                sx={{
                  fontFamily: DISPLAY,
                  fontWeight: 500,
                  color: fg.primary,
                  fontSize: { xs: 34, md: 54 },
                  lineHeight: 1.05,
                  letterSpacing: '-0.025em',
                }}
              >
                Take back your cloud data.
              </Typography>
              <Typography
                sx={{
                  fontFamily: SANS,
                  color: fg.muted,
                  fontSize: { xs: 17, md: 19 },
                  lineHeight: 1.6,
                  maxWidth: 560,
                  mx: 'auto',
                  mt: 2.5,
                }}
              >
                Set up your first private app in minutes. No ads, no tracking,
                no lock-in — and your data stays yours.
              </Typography>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                justifyContent="center"
                sx={{ mt: 4.5 }}
              >
                <Button
                  onClick={onSignup}
                  endIcon={<ArrowForwardRoundedIcon />}
                  sx={{
                    borderRadius: 999,
                    px: 4,
                    py: 1.5,
                    fontSize: 17,
                    fontWeight: 600,
                    color: '#fff',
                    background: 'linear-gradient(120deg, #2563EB, #7C5BFF 55%, #EC4899)',
                    boxShadow: '0 14px 40px rgba(124,91,255,0.4)',
                    transition: 'transform 0.2s, box-shadow 0.2s',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      boxShadow: '0 18px 48px rgba(124,91,255,0.5)',
                      background: 'linear-gradient(120deg, #1d4fd0, #6d4bf0 55%, #db3b89)',
                    },
                  }}
                >
                  Create your account
                </Button>
              </Stack>
            </Box>
          </Box>
        </Reveal>
      </Container>
    </Box>
  )
}

export default CtaBand
