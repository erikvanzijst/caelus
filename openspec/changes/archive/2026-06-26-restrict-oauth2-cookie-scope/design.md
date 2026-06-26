## Context

oauth2-proxy protects the Caelus app at the apex `${var.domain}` (e.g. `dev.freepod.eu` / `freepod.eu`) via a Traefik `forward-auth` middleware (`tf/app/caelus/ingress.tf:43`). The browser-facing `/oauth2/*` endpoints are served on a separate host, `login.${var.domain}`, and `redirect-url` points there (`tf/app/login/main.tf:30`). The session cookie is issued as `Domain=${var.domain}` (`cookie_domains`, `main.tf:22`).

User apps are deployed under the wildcard `*.${var.domain}`. A `Domain=${var.domain}` cookie is, per RFC 6265, sent to the apex **and all subdomains** — so the (already large, Keycloak-token-bearing, chunked `_oauth2_proxy_0/_1`) cookie reaches every user app's backend. Stale cookies under shifting domain scopes also accumulate, doubling header size and tripping `400 Request Header Or Cookie Too Large` at nginx.

## Goals / Non-Goals

**Goals:**
- The session cookie is host-only on `${var.domain}` and never sent to `*.${var.domain}`.
- Structurally prevent duplicate-scope accumulation (only one host can ever set the cookie).
- No change to the forward-auth authorization behavior for the Caelus app.

**Non-Goals:**
- Reducing the cookie's intrinsic size (Keycloak token trimming or Redis session store) — tracked separately; this change is about *scope*, not size.
- Decommissioning the `login.${var.domain}` DNS record / certificate (follow-up cleanup).

## Decisions

**Decision: Issue the cookie from the apex host, not `login.${var.domain}`.**
A host can only set a host-only cookie bound to *itself*. A host-only cookie set by `login.${var.domain}` would bind to `login.${var.domain}` and never reach the apex app. The only way the apex receives a cookie set by `login.` is a `Domain=${var.domain}` cookie — which unavoidably covers all subdomains. Therefore, to get a host-only apex cookie, the `/oauth2/callback` (and `/oauth2/start`) must run on `${var.domain}` itself.
- *Alternative considered — keep `login.` + `Domain` cookie:* cannot exclude subdomains; rejected (does not meet the goal).
- *Alternative considered — Redis session store:* shrinks the cookie but still leaves a `Domain` cookie leaking to subdomains; orthogonal to scope; deferred.

**Decision: Drop `cookie_domains` entirely** so oauth2-proxy emits no `Domain` attribute → host-only. Keep `whitelist_domains = ["${var.domain}"]` for open-redirect protection on `rd=`.

**Decision: Serve `/oauth2` on the apex via a dedicated Traefik route without `forward-auth`.** The existing `caelus-ingress` applies `forward-auth` to `/` (`ingress.tf:43`), which would intercept `/oauth2/*` before it reaches oauth2-proxy. A higher-priority route for `PathPrefix(/oauth2)` → oauth2-proxy service, carrying no auth middleware, keeps these endpoints reachable unauthenticated. This generalizes the existing `oauth2-signout` IngressRoute (`login/main.tf:83`) from `/oauth2/sign_out` to `/oauth2`.

## Risks / Trade-offs

- **Keycloak redirect-URI mismatch** → Update the `caelus-dev` client's *Valid Redirect URIs* and post-logout redirect to the apex callback **before/with** the apply, for both dev and prod, or login returns `invalid redirect_uri`.
- **Stale oversized cookies persist after deploy** → Host-only and `Domain` cookies are distinct entries; the old one is not overwritten. Mitigation: users clear `_oauth2_proxy*` once; optionally trigger a sign-out. New logins issue only the host-only cookie.
- **Route precedence regression** → If the apex `/oauth2` route does not out-prioritize the `/` forward-auth route, the endpoints become unreachable (redirect loop). Mitigation: verify with an unauthenticated `curl https://${var.domain}/oauth2/start` returning a 302 to Keycloak, not a forward-auth challenge.
- **Leftover `login.` ingress** → Harmless once unused; remove in follow-up to avoid confusion.

## Migration Plan

1. Update Keycloak `caelus-dev` Valid Redirect URIs + post-logout redirect → apex callback (dev + prod).
2. Apply Terraform: apex `/oauth2` route (no forward-auth), `redirect-url` → apex, remove `cookie_domains`.
3. Verify host-only cookie + working login/logout; confirm no cookie sent to a user-app subdomain.
4. Communicate one-time cookie clear to active users.
5. Follow-up: retire `login.${var.domain}` ingress and DNS/cert.

**Rollback:** revert the Terraform change (restore `login.` redirect-url + `cookie_domains`) and the Keycloak redirect URI; existing host-only cookies become inert and users re-login.
