/**
 * SPIKE — Google Photos → Immich migration feasibility probe (UI half).
 *
 * Uses the official @googleworkspace/drive-picker web component (via its intrinsic
 * <drive-picker> element, which supports a ref + the imperative `visible`
 * property). The refresh-token flow is unchanged: GIS *code* client (offline) →
 * backend exchanges + stores a refresh token → we hand the access token to the
 * picker via `oauth-token`. /probe still uses the server-side refresh token.
 */
import '@googleworkspace/drive-picker-element' // synchronously registers the <drive-picker> custom elements
import type {
  DrivePickerDocsViewElementProps,
  DrivePickerElement,
  DrivePickerElementProps,
} from '@googleworkspace/drive-picker-element'
import { Alert, Box, Button, Stack, Typography } from '@mui/material'
import { useCallback, useEffect, useState } from 'react'
import { requestJson } from '../../api/client'
import { config } from '../../config'

// The package augments the global `JSX` namespace, but the react-jsx transform
// resolves intrinsic elements via `React.JSX`, so declare them there. Inside
// `declare module 'react'`, RefAttributes/ReactNode resolve to React's own.
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'drive-picker': DrivePickerElementProps &
        RefAttributes<DrivePickerElement> & { children?: ReactNode }
      'drive-picker-docs-view': DrivePickerDocsViewElementProps
    }
  }
}

const CLIENT_ID = config.googleClientId
const API_KEY = config.googleApiKey
const APP_ID = config.googleAppId
const SCOPE = 'https://www.googleapis.com/auth/drive.file'

/* eslint-disable @typescript-eslint/no-explicit-any */
const w = window as any

// GIS is still needed for the offline *code* client (the component only does the
// implicit token flow, which yields no refresh token).
function ensureScript(src: string, id: string) {
  if (document.getElementById(id)) return
  const el = document.createElement('script')
  el.src = src
  el.id = id
  el.async = true
  document.head.appendChild(el)
}

function waitFor(pred: () => unknown, label: string, timeoutMs = 10_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const t0 = Date.now()
    const iv = setInterval(() => {
      if (pred()) {
        clearInterval(iv)
        resolve()
      } else if (Date.now() - t0 > timeoutMs) {
        clearInterval(iv)
        reject(new Error(`timed out waiting for ${label}`))
      }
    }, 50)
  })
}

interface ExchangeResult {
  access_token: string
  expires_in: number
  has_refresh_token: boolean
}

export default function GoogleTakeoutSpike() {
  const [gisReady, setGisReady] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [accessToken, setAccessToken] = useState('')
  const [hasRefresh, setHasRefresh] = useState<boolean | null>(null)
  const [probe, setProbe] = useState<unknown>(null)

  useEffect(() => {
    ensureScript('https://accounts.google.com/gsi/client', 'gsi-client')
    waitFor(() => w.google?.accounts?.oauth2, 'GIS oauth2')
      .then(() => setGisReady(true))
      .catch((e) => setError(String(e)))
  }, [])

  // Callback ref: when <drive-picker> mounts, wire its events and open it.
  const attachPicker = useCallback((el: DrivePickerElement | null) => {
    if (!el) return
    el.addEventListener('picker-picked', (e: any) => {
      const folder = e.detail?.docs?.[0]
      if (!folder) return
      setStatus(`Probing folder "${folder.name}" with the server-side refresh token…`)
      requestJson('/spike/google/probe', {
        method: 'POST',
        body: JSON.stringify({ folder_id: folder.id }),
      })
        .then((result) => {
          setProbe(result)
          setStatus('Probe complete.')
        })
        .catch((err) => setError(String(err)))
    })
    el.addEventListener('picker-canceled', () => setStatus('Picker canceled.'))
    el.addEventListener('picker-oauth-error', (e: any) =>
      setError('picker oauth error: ' + JSON.stringify(e?.detail)),
    )
    el.visible = true
  }, [])

  function connect() {
    setError('')
    setProbe(null)
    setStatus('Requesting drive.file consent…')
    const codeClient = w.google.accounts.oauth2.initCodeClient({
      client_id: CLIENT_ID,
      scope: SCOPE,
      ux_mode: 'popup',
      access_type: 'offline',
      prompt: 'consent',
      callback: async (resp: any) => {
        if (resp.error) return setError(`consent failed: ${resp.error}`)
        try {
          setStatus('Exchanging auth code for tokens (server-side)…')
          const r = await requestJson<ExchangeResult>('/spike/google/oauth', {
            method: 'POST',
            body: JSON.stringify({ code: resp.code, redirect_uri: 'postmessage' }),
          })
          setAccessToken(r.access_token)
          setHasRefresh(r.has_refresh_token)
          setStatus(
            r.has_refresh_token
              ? 'Refresh token stored. Opening picker…'
              : '⚠ No refresh token returned — revoke prior access and retry.',
          )
        } catch (e) {
          setError(String(e))
        }
      },
    })
    codeClient.requestCode()
  }

  const missingEnv = !CLIENT_ID || !API_KEY || !APP_ID

  return (
    <Box sx={{ maxWidth: 820, mx: 'auto', p: 4 }}>
      <Typography variant="h4" gutterBottom>
        Google Photos → Immich migration spike
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Official <code>@googleworkspace/drive-picker</code> component. Validates that a{' '}
        <code>drive.file</code> + Picker grant lets freepod's <em>server</em> list and download a
        picked Takeout folder using only an offline refresh token.
      </Typography>

      {missingEnv && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Missing Google config — check <code>window.__ENV__</code> / build env.
        </Alert>
      )}

      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <Button variant="contained" onClick={connect} disabled={!gisReady || missingEnv}>
          Connect Google Drive & pick Takeout folder
        </Button>
      </Stack>

      {status && <Alert severity="info" sx={{ mb: 2 }}>{status}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {hasRefresh === false && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Google withheld a refresh token. Revoke at{' '}
          <a href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">
            myaccount.google.com/permissions
          </a>{' '}
          and retry.
        </Alert>
      )}

      {/* Rendered once we hold a token; opened via the visible property in the ref. */}
      {accessToken && (
        <drive-picker
          ref={attachPicker}
          client-id={CLIENT_ID}
          app-id={APP_ID}
          developer-key={API_KEY}
          oauth-token={accessToken}
          title="Pick your Google Takeout folder"
        >
          <drive-picker-docs-view
            select-folder-enabled="true"
            include-folders="true"
            mime-types="application/vnd.google-apps.folder"
          />
        </drive-picker>
      )}

      {probe != null && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6">Probe result</Typography>
          <Box
            component="pre"
            sx={{
              mt: 1,
              p: 2,
              bgcolor: 'grey.900',
              color: 'grey.100',
              borderRadius: 1,
              overflow: 'auto',
              fontSize: 13,
            }}
          >
            {JSON.stringify(probe, null, 2)}
          </Box>
        </Box>
      )}
    </Box>
  )
}
