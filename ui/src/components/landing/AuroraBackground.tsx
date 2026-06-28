import { Box } from '@mui/material'
import { accent, ink } from './landingTokens'

export type AuroraPreset = 'whisper' | 'balanced' | 'vivid' | 'nebula'
export type AuroraTemperature = 'cool' | 'warm'

interface AuroraBackgroundProps {
  /** Dim the aurora for use behind dense content (e.g. the CTA band). */
  subtle?: boolean
  /** Intensity preset. Defaults to 'balanced'. */
  preset?: AuroraPreset
  /** Colour temperature. Defaults to 'warm'. */
  temperature?: AuroraTemperature
}

/** Three bloom colours per temperature: [primary, secondary, accent]. */
const TEMPS: Record<AuroraTemperature, [string, string, string]> = {
  cool: [accent.blue, accent.cyan, accent.magenta],
  warm: [accent.magenta, accent.pink, accent.blue],
}

interface PresetConfig {
  /** Hex alpha suffixes for the three blooms. */
  alphas: [string, string, string]
  blur: number
  /** Bloom diameters in vw. */
  sizes: [number, number, number]
  /** Drift animation durations in seconds. */
  drift: [number, number, number]
  grid: number
  grain: number
  /** Nebula-only extras: a bright highlight bloom + vignette. */
  extra?: boolean
}

const PRESETS: Record<AuroraPreset, PresetConfig> = {
  whisper: { alphas: ['33', '26', '1f'], blur: 56, sizes: [64, 56, 52], drift: [34, 40, 36], grid: 0.16, grain: 0.22 },
  balanced: { alphas: ['55', '44', '33'], blur: 42, sizes: [70, 60, 55], drift: [22, 28, 25], grid: 0.32, grain: 0.4 },
  vivid: { alphas: ['80', '66', '55'], blur: 30, sizes: [76, 66, 60], drift: [18, 22, 20], grid: 0.4, grain: 0.48 },
  nebula: { alphas: ['99', '80', '66'], blur: 26, sizes: [82, 72, 66], drift: [15, 19, 17], grid: 0.46, grain: 0.58, extra: true },
}

/**
 * Layered, slowly drifting radial "aurora" plus a faint grid and grain.
 * Sits behind hero / CTA content to give atmosphere and depth instead of a
 * flat fill. Pointer-events are disabled so it never blocks interaction.
 */
export function AuroraBackground({ subtle = false, preset, temperature }: AuroraBackgroundProps) {
  const activePreset = preset ?? 'balanced'
  const activeTemp = temperature ?? 'warm'

  const cfg = PRESETS[activePreset]
  const [c1, c2, c3] = TEMPS[activeTemp]
  const opacity = subtle ? 0.5 : 1

  return (
    <Box
      aria-hidden
      sx={{
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        background: ink.base,
      }}
    >
      {/* Drifting colour blooms */}
      <Box
        sx={{
          position: 'absolute',
          top: '-22%',
          left: '-10%',
          width: `${cfg.sizes[0]}vw`,
          height: `${cfg.sizes[0]}vw`,
          opacity,
          background: `radial-gradient(circle, ${c1}${cfg.alphas[0]}, transparent 62%)`,
          filter: `blur(${cfg.blur}px)`,
          animation: `lp-aurora-drift ${cfg.drift[0]}s ease-in-out infinite`,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          top: '-10%',
          right: '-15%',
          width: `${cfg.sizes[1]}vw`,
          height: `${cfg.sizes[1]}vw`,
          opacity,
          background: `radial-gradient(circle, ${c3}${cfg.alphas[1]}, transparent 60%)`,
          filter: `blur(${cfg.blur}px)`,
          animation: `lp-aurora-drift ${cfg.drift[1]}s ease-in-out infinite reverse`,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          bottom: '-30%',
          left: '20%',
          width: `${cfg.sizes[2]}vw`,
          height: `${cfg.sizes[2]}vw`,
          opacity,
          background: `radial-gradient(circle, ${c2}${cfg.alphas[2]}, transparent 60%)`,
          filter: `blur(${cfg.blur + 6}px)`,
          animation: `lp-aurora-drift ${cfg.drift[2]}s ease-in-out infinite`,
        }}
      />
      {/* Nebula-only: bright central highlight */}
      {cfg.extra && (
        <Box
          sx={{
            position: 'absolute',
            top: '-6%',
            left: '38%',
            width: '34vw',
            height: '34vw',
            opacity,
            background: `radial-gradient(circle, ${c2}55, transparent 60%)`,
            filter: `blur(${cfg.blur}px)`,
            animation: 'lp-aurora-drift 13s ease-in-out infinite reverse',
          }}
        />
      )}
      {/* Faint engineering grid */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          opacity: cfg.grid,
          backgroundImage:
            'linear-gradient(rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.06) 1px, transparent 1px)',
          backgroundSize: '54px 54px',
          maskImage: 'radial-gradient(ellipse at center, #000 30%, transparent 78%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, #000 30%, transparent 78%)',
        }}
      />
      {/* Grain for texture */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          opacity: cfg.grain,
          mixBlendMode: 'overlay',
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
      {/* Nebula-only: vignette for depth */}
      {cfg.extra && (
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            background: 'radial-gradient(ellipse at center, transparent 45%, rgba(3,5,12,0.55) 100%)',
          }}
        />
      )}
      {/* Bottom fade into page background */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(to bottom, transparent 55%, ${ink.base} 98%)`,
        }}
      />
    </Box>
  )
}

export default AuroraBackground
