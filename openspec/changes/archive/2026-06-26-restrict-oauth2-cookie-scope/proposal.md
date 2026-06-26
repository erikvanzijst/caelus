## Why

The oauth2-proxy session cookie is currently issued as a `Domain=${var.domain}` cookie, which the browser sends to the apex **and every wildcard user-app subdomain** under it. Because the cookie is set by the `login.${var.domain}` callback host, the scope cannot be narrowed without re-architecting where the cookie is issued. The broad scope, combined with stale cookies accumulating across changing domain scopes, produces oversized `Cookie` headers (Keycloak tokens chunked across `_oauth2_proxy_0/_1`, then duplicated), which trips `400 Request Header Or Cookie Too Large` at nginx in the ingress/app path.

## What Changes

- Move the browser-facing `/oauth2/*` endpoints (`start`, `callback`, `sign_out`) from `login.${var.domain}` onto the Caelus apex host `${var.domain}`, routed directly to the oauth2-proxy service **without** the `forward-auth` middleware.
- Point `redirect-url` at `https://${var.domain}/oauth2/callback` so the cookie is issued by the apex host itself.
- Drop `cookie_domains` so oauth2-proxy emits a **host-only** cookie (no `Domain` attribute), scoped to `${var.domain}` only and never sent to `*.${var.domain}` user apps.
- Retain `whitelist_domains = ["${var.domain}"]` for redirect-target safety.
- **BREAKING** (operational): the Keycloak `caelus-dev` client's *Valid Redirect URIs* and post-logout redirect must be updated to the apex callback. Existing sessions must be re-established (users clear stale `_oauth2_proxy*` cookies once).
- Retire the now-unused `login.${var.domain}` Helm ingress for cookie issuance (DNS/cert cleanup is follow-up, non-blocking).

## Capabilities

### New Capabilities
<!-- None: this change modifies existing oauth2-proxy session/cookie behavior. -->

### Modified Capabilities
- `oauth2-proxy-deployment`: session cookie scope changes from a domain cookie (`Domain=${var.domain}`, covering all subdomains) to a host-only cookie scoped to the Caelus apex; browser-facing `/oauth2/*` endpoints move from `login.${var.domain}` to the apex host; `redirect-url` targets the apex callback.

## Impact

- **Terraform**: `tf/app/login/main.tf` (oauth2-proxy `configFile`/`extraArgs`, `/oauth2` IngressRoute, retire `login.` ingress), `tf/app/caelus/ingress.tf` (ensure `/oauth2` prefix on apex bypasses `forward-auth`).
- **External / Keycloak**: `caelus-dev` client Valid Redirect URIs + post-logout redirect URI (manual change, both dev and prod).
- **Users**: one-time clearing of stale oversized cookies; re-login.
- **Downstream apps**: wildcard user-app subdomains stop receiving the oauth2-proxy cookie entirely, eliminating oversized-header `400`s on those backends.
