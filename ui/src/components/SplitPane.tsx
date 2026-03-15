import { useCallback, useRef, useState } from 'react'
import { Box } from '@mui/material'

interface SplitPaneProps {
  left: React.ReactNode
  right: React.ReactNode
  defaultLeftPercent?: number
  minLeftPercent?: number
  maxLeftPercent?: number
}

export function SplitPane({
  left,
  right,
  defaultLeftPercent = 50,
  minLeftPercent = 25,
  maxLeftPercent = 75,
}: SplitPaneProps) {
  const [leftPercent, setLeftPercent] = useState(defaultLeftPercent)
  const containerRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      dragging.current = true

      const onMouseMove = (ev: MouseEvent) => {
        if (!dragging.current || !containerRef.current) return
        const rect = containerRef.current.getBoundingClientRect()
        const x = ev.clientX - rect.left
        const pct = (x / rect.width) * 100
        setLeftPercent(Math.min(maxLeftPercent, Math.max(minLeftPercent, pct)))
      }

      const onMouseUp = () => {
        dragging.current = false
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('mouseup', onMouseUp)
      }

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    },
    [minLeftPercent, maxLeftPercent],
  )

  return (
    <Box
      ref={containerRef}
      sx={{
        display: 'flex',
        gap: 0,
        minHeight: 300,
      }}
    >
      <Box sx={{ width: `${leftPercent}%`, minWidth: 0, overflow: 'hidden' }}>
        {left}
      </Box>
      <Box
        onMouseDown={onMouseDown}
        sx={{
          width: 8,
          flexShrink: 0,
          cursor: 'col-resize',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          '&:hover > div, &:active > div': {
            bgcolor: 'primary.main',
          },
        }}
      >
        <Box
          sx={{
            width: 3,
            height: 40,
            borderRadius: 1,
            bgcolor: 'divider',
            transition: 'background-color 0.15s',
          }}
        />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
        {right}
      </Box>
    </Box>
  )
}
