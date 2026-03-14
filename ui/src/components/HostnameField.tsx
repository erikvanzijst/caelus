import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Box,
  CircularProgress,
  FormControl,
  FormHelperText,
  InputAdornment,
  MenuItem,
  Select,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import { checkHostname } from '../api/endpoints'

const DEBOUNCE_MS = 400

const REASON_LABELS: Record<string, string> = {
  invalid: 'Invalid hostname format',
  reserved: 'Hostname is reserved',
  in_use: 'Already in use',
  not_resolving: 'Does not resolve to Caelus',
}

type ValidationState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'valid' }
  | { status: 'error'; reason: string }

interface HostnameFieldProps {
  value: string
  onChange: (hostname: string) => void
  wildcardDomains: string[]
  required?: boolean
  error?: string
  description?: string
}

type Mode = 'wildcard' | 'custom'

export function HostnameField({ value, onChange, wildcardDomains, required, error, description }: HostnameFieldProps) {
  const hasWildcard = wildcardDomains.length > 0
  const [mode, setMode] = useState<Mode>(hasWildcard ? 'wildcard' : 'custom')
  const [prefix, setPrefix] = useState('')
  const [domain, setDomain] = useState(wildcardDomains[0] ?? '')
  const [customFqdn, setCustomFqdn] = useState('')
  const [validation, setValidation] = useState<ValidationState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync wildcard domains into local state when they arrive asynchronously
  const domainsInitializedRef = useRef(hasWildcard)
  useEffect(() => {
    if (domainsInitializedRef.current || !hasWildcard) return
    domainsInitializedRef.current = true
    setMode('wildcard')
    setDomain(wildcardDomains[0])
  }, [hasWildcard, wildcardDomains])

  // Sync initial value into local state on mount
  const initializedRef = useRef(false)
  useEffect(() => {
    if (initializedRef.current || !value) return
    initializedRef.current = true

    if (hasWildcard) {
      const matchingDomain = wildcardDomains.find((d) => value.endsWith(`.${d}`))
      if (matchingDomain) {
        setPrefix(value.slice(0, -(matchingDomain.length + 1)))
        setDomain(matchingDomain)
        setMode('wildcard')
        return
      }
    }
    setCustomFqdn(value)
    setMode('custom')
  }, [value, hasWildcard, wildcardDomains])

  const currentFqdn = mode === 'wildcard' ? (prefix ? `${prefix}.${domain}` : '') : customFqdn

  const validate = useCallback((fqdn: string) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (abortRef.current) abortRef.current.abort()

    if (!fqdn) {
      setValidation({ status: 'idle' })
      return
    }

    setValidation({ status: 'checking' })
    const controller = new AbortController()
    abortRef.current = controller

    timerRef.current = setTimeout(async () => {
      try {
        const result = await checkHostname(fqdn)
        if (controller.signal.aborted) return
        if (result.usable) {
          setValidation({ status: 'valid' })
        } else {
          setValidation({ status: 'error', reason: result.reason ?? 'invalid' })
        }
      } catch {
        if (controller.signal.aborted) return
        setValidation({ status: 'error', reason: 'invalid' })
      }
    }, DEBOUNCE_MS)
  }, [])

  // Trigger validation and propagate value when the computed FQDN changes
  const prevFqdnRef = useRef(currentFqdn)
  useEffect(() => {
    if (prevFqdnRef.current === currentFqdn) return
    prevFqdnRef.current = currentFqdn
    onChange(currentFqdn)
    validate(currentFqdn)
  }, [currentFqdn, onChange, validate])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (abortRef.current) abortRef.current.abort()
    }
  }, [])

  const handleModeChange = (_: unknown, newMode: Mode | null) => {
    if (!newMode) return
    setMode(newMode)
    setValidation({ status: 'idle' })
    if (newMode === 'wildcard') {
      setCustomFqdn('')
    } else {
      setPrefix('')
    }
  }

  const statusAdornment = (() => {
    switch (validation.status) {
      case 'checking':
        return (
          <InputAdornment position="end">
            <CircularProgress size={20} />
          </InputAdornment>
        )
      case 'valid':
        return (
          <InputAdornment position="end">
            <CheckCircleIcon color="success" />
          </InputAdornment>
        )
      case 'error':
        return (
          <InputAdornment position="end">
            <Tooltip title={REASON_LABELS[validation.reason] ?? validation.reason}>
              <ErrorIcon color="error" />
            </Tooltip>
          </InputAdornment>
        )
      default:
        return null
    }
  })()

  const helperText =
    error ??
    (validation.status === 'error' ? REASON_LABELS[validation.reason] ?? validation.reason : undefined) ??
    description

  return (
    <FormControl fullWidth error={!!error || validation.status === 'error'}>
        {mode === 'wildcard' ? (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
            <TextField
              label="Hostname"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              required={required}
              error={!!error || validation.status === 'error'}
              slotProps={{ input: { endAdornment: statusAdornment } }}
              sx={{ flex: 1 }}
            />
            <Typography sx={{ mb: 2 }}>.</Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, minWidth: 180 }}>
              {hasWildcard && (
                <ToggleButtonGroup
                  value={mode}
                  exclusive
                  onChange={handleModeChange}
                  size="small"
                  fullWidth
                >
                  <ToggleButton value="wildcard" sx={{ whiteSpace: 'nowrap' }}>
                    <Typography variant="caption">Free domain</Typography>
                  </ToggleButton>
                  <ToggleButton value="custom" sx={{ whiteSpace: 'nowrap' }}>
                    <Typography variant="caption">Custom domain</Typography>
                  </ToggleButton>
                </ToggleButtonGroup>
              )}
              <Select
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              >
                {wildcardDomains.map((d) => (
                  <MenuItem key={d} value={d}>
                    {d}
                  </MenuItem>
                ))}
              </Select>
            </Box>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {hasWildcard && (
              <ToggleButtonGroup
                value={mode}
                exclusive
                onChange={handleModeChange}
                size="small"
                sx={{ alignSelf: 'flex-end' }}
              >
                <ToggleButton value="wildcard">
                  <Typography variant="caption">Free domain</Typography>
                </ToggleButton>
                <ToggleButton value="custom">
                  <Typography variant="caption">Custom domain</Typography>
                </ToggleButton>
              </ToggleButtonGroup>
            )}
            <TextField
              label="Hostname"
              value={customFqdn}
              onChange={(e) => setCustomFqdn(e.target.value)}
              placeholder="myapp.example.com"
              required={required}
              error={!!error || validation.status === 'error'}
              slotProps={{ input: { endAdornment: statusAdornment } }}
              fullWidth
            />
          </Box>
        )}

        {helperText && <FormHelperText>{helperText}</FormHelperText>}
    </FormControl>
  )
}
