## 1. Keycloak (manual, external)

- [x] 1.1 Add `https://${var.domain}/oauth2/callback` to the `caelus-dev` client's Valid Redirect URIs for **dev** (`dev.freepod.eu`)
- [x] 1.2 Add `https://freepod.eu/oauth2/callback` to the `caelus-dev` client's Valid Redirect URIs for **prod**
- [x] 1.3 Update the post-logout / Valid Post Logout Redirect URIs to the apex host for dev and prod

## 2. oauth2-proxy configuration (tf/app/login/main.tf)

- [x] 2.1 Change `redirect-url` from `https://login.${var.domain}/oauth2/callback` to `https://${var.domain}/oauth2/callback`
- [x] 2.2 Remove `cookie_domains` from the `configFile` so the cookie is emitted host-only (no `Domain` attribute); keep `whitelist_domains = ["${var.domain}"]`
- [x] 2.3 Generalize the `oauth2-signout` IngressRoute from `PathPrefix(\`/oauth2/sign_out\`)` to `PathPrefix(\`/oauth2\`)` on `Host(\`${var.domain}\`)`, routing to the oauth2-proxy service (no `forward-auth` middleware) — renamed to `oauth2-endpoints`
- [x] 2.4 Remove / disable the Helm chart `ingress` block that serves `/oauth2` on `login.${var.domain}` (no longer used for cookie issuance)

## 3. Apex routing (tf/app/caelus/ingress.tf)

- [x] 3.1 Ensure the apex `/oauth2` route out-prioritizes the `/` route carrying `forward-auth`, so `/oauth2/*` reaches oauth2-proxy unauthenticated (no auth challenge / redirect loop) — `priority = 100` on the IngressRoute + cross-reference comment on the caelus ingress

## 4. Validation

- [x] 4.1 `terraform plan` (dev workspace) reviewed: intended cookie changes confirmed (helm_release update, `oauth2-endpoints` route created, `oauth2-signout` destroyed). NOTE: plan also includes pre-existing unrelated drift — `configmap.api` CNAME rebrand (`CAELUS_DOMAIN`/`CAELUS_LB_IPS`) and `restartedAt` annotation removal on api/ui/worker deployments. Decide whether to apply together or target-apply only the oauth2 resources.
- [x] 4.2 Host-only cookie confirmed: `/oauth2/start` sets `_oauth2_proxy_csrf` with **no** `Domain` attribute (`Path=/; Max-Age=900; HttpOnly`). Same cookie config governs the `_oauth2_proxy` session cookie at callback. Final session-cookie check folds into 4.5 (interactive login).
- [x] 4.3 `https://dev.freepod.eu/oauth2/start` (unauthenticated) returns `302` → Keycloak with `redirect_uri=…/oauth2/callback` on the apex; app root `/` still challenges via forward-auth. No redirect loop.
- [x] 4.4 Structurally guaranteed: a host-only cookie (no `Domain`) is never sent to `*.${var.domain}` per RFC 6265 — confirmed by the host-only `Set-Cookie` in 4.2.
- [x] 4.5 Login → app access → logout round-trip verified working (prod tested by user; dev validated via curl + identical flow)

## 5. Rollout

- [x] 5.1 Communicate one-time `_oauth2_proxy*` cookie clear to active users
- [x] 5.2 Repeat apply + validation on prod (`freepod.eu`)
- [x] 5.3 No-op: `login.${var.domain}` had no dedicated cert or DNS record — both are wildcards (`*.${var.domain}`) still in use. Disabling the chart ingress (2.4) fully retires the host; nothing further to remove.
