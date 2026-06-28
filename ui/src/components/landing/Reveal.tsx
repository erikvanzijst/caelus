import { useEffect, useRef, useState, type PropsWithChildren } from 'react'
import { Box, type BoxProps } from '@mui/material'

interface RevealProps extends BoxProps {
  /** Delay (ms) before the reveal transition starts once in view. */
  delay?: number
}

/**
 * Wraps content and fades/slides it into view the first time it enters the
 * viewport. Uses IntersectionObserver (no animation library) and respects
 * prefers-reduced-motion via the .lp-reveal CSS in index.css.
 */
export function Reveal({ delay = 0, children, sx, ...rest }: PropsWithChildren<RevealProps>) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true)
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <Box
      ref={ref}
      className={`lp-reveal${visible ? ' is-visible' : ''}`}
      sx={{ transitionDelay: `${delay}ms`, ...sx }}
      {...rest}
    >
      {children}
    </Box>
  )
}

export default Reveal
