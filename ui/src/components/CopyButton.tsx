import { useEffect, useRef, useState } from 'react'
import { IconButton, Tooltip } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import CheckIcon from '@mui/icons-material/Check'

interface CopyButtonProps {
  value: string
  /** Names the thing in the tooltip and the accessible label, e.g. "password". */
  label: string
  size?: 'small' | 'medium'
}

/**
 * Copy-to-clipboard affordance with a brief confirmation tick. Shared so every
 * copyable technical value in the app behaves and reads identically.
 */
export function CopyButton({ value, label, size = 'small' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => () => clearTimeout(timer.current), [])

  return (
    <Tooltip title={copied ? 'Copied' : `Copy ${label}`}>
      <IconButton
        size={size}
        aria-label={`Copy ${label}`}
        onClick={() => {
          void navigator.clipboard.writeText(value)
          setCopied(true)
          clearTimeout(timer.current)
          timer.current = setTimeout(() => setCopied(false), 1500)
        }}
      >
        {copied ? <CheckIcon fontSize="inherit" /> : <ContentCopyIcon fontSize="inherit" />}
      </IconButton>
    </Tooltip>
  )
}

export default CopyButton
