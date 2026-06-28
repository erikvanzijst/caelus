import { Box, Button, Chip, Container, Stack, Typography } from '@mui/material'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import {
  accent,
  DISPLAY,
  fg,
  MONO,
  SANS,
} from './landingTokens'
import AuroraBackground from './AuroraBackground'
import { resolveApiPath } from '../../api/client'
import { useLandingProducts } from './useLandingProducts'

interface HeroProps {
  onSignup: () => void
}

const trustPoints = ['EU-hosted', 'No ads, ever', 'Open source', 'Export anytime']

/** Build-up: staggered fade for the hero stack on first paint. */
const reveal = (i: number) => ({
  opacity: 0,
  animation: 'lp-fade-up 0.85s cubic-bezier(0.22,1,0.36,1) forwards',
  animationDelay: `${0.1 + i * 0.12}s`,
})

export function Hero({ onSignup }: HeroProps) {
  const { data: products } = useLandingProducts()

  return (
    <Box component="section" sx={{ position: 'relative', overflow: 'hidden' }}>
      <AuroraBackground />

      <Container
        maxWidth="md"
        sx={{
          position: 'relative',
          zIndex: 1,
          textAlign: 'center',
          pt: { xs: 9, md: 14 },
          pb: { xs: 10, md: 16 },
        }}
      >
        {/* Eyebrow */}
        <Box sx={reveal(0)}>
          <Typography
            component="p"
            sx={{
              fontFamily: MONO,
              fontSize: 13,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: accent.cyan,
              mb: 3,
            }}
          >
            The European cloud · Open source · No lock-in
          </Typography>
        </Box>

        {/* Headline */}
        <Box sx={reveal(1)}>
          <Typography
            component="h1"
            sx={{
              fontFamily: DISPLAY,
              fontWeight: 500,
              color: fg.primary,
              fontSize: { xs: 46, sm: 64, md: 80 },
              lineHeight: 1.02,
              letterSpacing: '-0.025em',
            }}
          >
            Your digital life,
            <br />
            finally{' '}
            <Box
              component="em"
              sx={{
                fontStyle: 'italic',
                backgroundImage: `linear-gradient(120deg, ${accent.blue}, ${accent.pink})`,
                WebkitBackgroundClip: 'text',
                backgroundClip: 'text',
                color: 'transparent',
              }}
            >
              yours.
            </Box>
          </Typography>
        </Box>

        {/* Subhead */}
        <Box sx={reveal(2)}>
          <Typography
            sx={{
              fontFamily: SANS,
              color: fg.muted,
              fontSize: { xs: 17, md: 20 },
              lineHeight: 1.6,
              maxWidth: 660,
              mx: 'auto',
              mt: 3.5,
            }}
          >
            Freepod runs private, dedicated instances (pods) of the best open-source
            apps — your photos, files, chat and passwords — hosted in Europe.
            No ads. No tracking. No holding your data hostage. Take everything
            with you, any time you like.
          </Typography>
        </Box>

        {/* CTAs */}
        <Box sx={reveal(3)}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            justifyContent="center"
            sx={{ mt: 5 }}
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
                  background:
                    'linear-gradient(120deg, #1d4fd0, #6d4bf0 55%, #db3b89)',
                },
              }}
            >
              Create your account
            </Button>
            <Button
              href="#apps"
              sx={{
                borderRadius: 999,
                px: 3.5,
                py: 1.5,
                fontSize: 17,
                fontWeight: 600,
                color: fg.primary,
                border: '1px solid rgba(255,255,255,0.18)',
                background: 'rgba(255,255,255,0.03)',
                '&:hover': {
                  background: 'rgba(255,255,255,0.08)',
                  borderColor: 'rgba(255,255,255,0.3)',
                },
              }}
            >
              Explore the apps
            </Button>
          </Stack>
        </Box>

        {/* Trust strip */}
        <Box sx={reveal(4)}>
          <Stack
            direction="row"
            flexWrap="wrap"
            justifyContent="center"
            spacing={1.25}
            useFlexGap
            sx={{ mt: 5 }}
          >
            {trustPoints.map((point) => (
              <Chip
                key={point}
                label={point}
                size="small"
                sx={{
                  fontFamily: SANS,
                  color: fg.muted,
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  px: 0.5,
                }}
              />
            ))}
          </Stack>
        </Box>

        {/* App constellation preview */}
        <Box sx={reveal(5)}>
          <Stack
            direction="row"
            flexWrap="wrap"
            justifyContent="center"
            spacing={1.5}
            useFlexGap
            sx={{ mt: 7 }}
          >
            {(products ?? []).map((product) => (
              <Stack
                key={product.id}
                direction="row"
                alignItems="center"
                spacing={1}
                sx={{
                  px: 2,
                  py: 1,
                  borderRadius: 999,
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  backdropFilter: 'blur(8px)',
                }}
              >
                {product.iconUrl && (
                  <Box
                    component="img"
                    src={resolveApiPath(product.iconUrl)}
                    alt=""
                    sx={{ width: 18, height: 18, objectFit: 'contain' }}
                  />
                )}
                <Typography
                  sx={{ fontFamily: SANS, fontSize: 14, color: fg.primary }}
                >
                  {product.name}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Box>
      </Container>
    </Box>
  )
}

export default Hero
