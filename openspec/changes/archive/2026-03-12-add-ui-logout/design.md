## Context

Caelus authentication is handled entirely outside the application by
oauth2-proxy (reverse-proxy session cookie) and Keycloak (OIDC identity
provider). Two independent sessions exist:

1. **oauth2-proxy cookie** (`_oauth2_proxy`) — set on the `.app.deprutser.be`
   domain, validated by the Traefik forward-auth middleware on every request.
2. **Keycloak SSO session** (`KEYCLOAK_SESSION`) — lives on the
   `keycloak.app.deprutser.be` domain, survives until explicit logout or
   expiry.

Clearing only the proxy cookie leaves the Keycloak session alive. The next
request triggers the forward-auth → 401 → oauth-errors redirect chain, which
sends the browser to Keycloak. Because the SSO session is still valid, Keycloak
immediately issues a new token and redirects back — the user never sees a login
screen.

## Goals / Non-Goals

**Goals:**
- One-click logout that terminates both sessions and lands the user on the
  Keycloak login page.
- Same-origin `/oauth2/sign_out` URL so the frontend uses a relative path.
- Graceful local-dev logout that clears localStorage headers and re-shows the
  email dialog.

**Non-Goals:**
- Backchannel logout (Keycloak-initiated session revocation propagated to
  oauth2-proxy). oauth2-proxy does not support this; out of scope.
- Parameterizing the Keycloak URL across environments (both `oidc-issuer-url`
  and the new `backend-logout-url` already hardcode the shared Keycloak
  instance; acceptable for now).
- Adding other account-management UI (profile, password change, etc.).

## Decisions

### 1. Use `--backend-logout-url` (server-side) over `rd`-chained browser redirect

**Decision:** Configure `--backend-logout-url` with `{id_token}` placeholder so
oauth2-proxy calls Keycloak's logout endpoint server-side.

**Rationale:** The alternative — redirecting the browser to Keycloak's logout
endpoint via the `rd` parameter — cannot include `id_token_hint` (oauth2-proxy
intentionally does not substitute tokens in `rd` for security reasons). Without
`id_token_hint`, Keycloak 18+ shows a "Do you want to log out?" confirmation
screen, which is poor UX. The server-side call passes the real token securely
and Keycloak terminates the session silently.

**Alternatives considered:**
- `rd` redirect to Keycloak logout: Works on all oauth2-proxy versions but
  produces a confirmation screen on Keycloak 18+ (we run 24.0).
- Keycloak's `suppress-logout-confirmation-screen` SPI flag: Scheduled for
  removal, not a stable solution.

### 2. Expose `/oauth2/sign_out` on the app domain via IngressRoute

**Decision:** Create a Traefik `IngressRoute` CRD in the login namespace that
matches `Host(var.domain) && PathPrefix(/oauth2/sign_out)` and routes to the
oauth2-proxy service without auth middleware.

**Rationale:** The frontend can then use a simple relative URL
(`/oauth2/sign_out?rd=...`) without knowing the `login.*` subdomain. The
IngressRoute lives in the login namespace alongside oauth2-proxy, so the
service reference is local — no cross-namespace plumbing needed. Traefik
automatically prioritizes the longer path match over the catch-all `/` in the
Caelus ingress.

**Alternatives considered:**
- Navigate to `login.app.deprutser.be/oauth2/sign_out`: Works (cookie domain
  `.app.deprutser.be` covers subdomains) but couples the frontend to the login
  subdomain naming convention. Kept as fallback if the IngressRoute causes
  middleware conflicts.
- Backend API redirect endpoint (`GET /api/auth/logout` → 302): Adds an API
  endpoint and requires the backend to know the domain config. Unnecessary
  indirection.

### 3. No auth middleware on the sign_out IngressRoute

**Decision:** The IngressRoute for `/oauth2/sign_out` does NOT use the
forward-auth or oauth-errors middleware.

**Rationale:** The sign_out endpoint is handled entirely by oauth2-proxy. It
reads the session cookie directly to extract the id_token for the backend
logout call. Wrapping it in forward-auth would add a redundant auth check. More
importantly, after the cookie is cleared, a forward-auth check would fail and
the oauth-errors middleware could interfere with the redirect.

### 4. Detect local dev via localStorage auth headers

**Decision:** If `getStoredAuthHeaders()` returns a non-empty object, the app
is in local-dev mode (no oauth2-proxy). Logout clears the stored headers and
reloads the page.

**Rationale:** In production, oauth2-proxy injects headers server-side;
localStorage is empty. In local dev, the `EmailDialog` stores
`X-Auth-Request-Email` in localStorage. This is an existing, reliable signal
that requires no additional configuration flags.

**Alternatives considered:**
- Environment variable / build-time flag: Requires build config changes. The
  localStorage approach is already implicit in the existing code.
- Hide logout button in local dev: Less realistic dev experience; the button
  should be testable locally.

## Risks / Trade-offs

**[Risk]** oauth2-proxy session-ordering bug (PR #3352, still open) could cause
`--backend-logout-url` to fail silently if the session is cleared before the
backend call.
→ **Mitigation:** Confirmed working on v7.14.2 (our version) with legacy
config + CLI flags per issue #3172 comment. End-to-end test with Playwright
will catch regressions. Fallback: revert to Approach A (`rd` → Keycloak logout
with confirmation screen).

**[Risk]** Traefik IngressRoute priority conflict with the Caelus ingress
catch-all `/` route.
→ **Mitigation:** Traefik defaults to higher priority for longer path rules.
If conflicts arise, add an explicit `priority` field to the IngressRoute. If
IngressRoute approach proves problematic, fall back to cross-domain navigate to
`login.${domain}`.

**[Risk]** Keycloak `caelus-dev` client may not have valid post-logout redirect
URIs configured.
→ **Mitigation:** Manual admin console step documented in proposal. Not
strictly required for `--backend-logout-url` (server-side call does not
redirect), but good practice.
