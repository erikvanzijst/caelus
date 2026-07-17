// Runtime configuration reader.
//
// Two sources, in priority order:
//   1. window.__ENV__  — injected at container startup from the pod env (the ui
//      ConfigMap), via /config.js which index.html loads before this bundle.
//   2. import.meta.env — Vite's build-time values (.env / .env.local), used in
//      local dev where /config.js is the empty public/ stub.
//
// A non-empty runtime value always wins; otherwise we fall back to build time.
// This is what lets one built image be configured per-environment at deploy.

declare global {
  interface Window {
    __ENV__?: Record<string, string | undefined>
  }
}

const runtime: Record<string, string | undefined> =
  (typeof window !== 'undefined' && window.__ENV__) || {}

function pick(runtimeValue: string | undefined, buildValue: string | undefined): string | undefined {
  return runtimeValue && runtimeValue.length > 0 ? runtimeValue : buildValue
}

// Only the runtime-injected vars belong here. VITE_API_URL is deliberately not
// included — it's a build-time value (.env / .env.production); see api/client.ts.
export const config = {
  googleClientId: pick(
    runtime.VITE_GOOGLE_CLIENT_ID,
    import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined,
  ),
  googleApiKey: pick(
    runtime.VITE_GOOGLE_API_KEY,
    import.meta.env.VITE_GOOGLE_API_KEY as string | undefined,
  ),
  googleAppId: pick(
    runtime.VITE_GOOGLE_APP_ID,
    import.meta.env.VITE_GOOGLE_APP_ID as string | undefined,
  ),
}
