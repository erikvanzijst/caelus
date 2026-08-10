## 1. Keycloak: audience client scopes (`tf/deps`)

- [x] 1.1 Add a `freepod-api-prod` client scope in
  `tf/deps/keycloak-config/scopes.tf` with `include_in_token_scope = false`
  (it rides along as a default scope and should stay out of the `scope` claim,
  matching the existing `groups` scope).
- [x] 1.2 Add a `keycloak_openid_audience_protocol_mapper` on that scope with
  `included_client_audience` pointing at the `freepod_prod` client and
  `add_to_access_token = true`. Comment it as security-critical: it is the only
  thing separating a prod token from a dev one (design.md D2/D3).
- [x] 1.3 Repeat 1.1–1.2 for `freepod-api-dev` against the `freepod_dev` client.
- [x] 1.4 Confirm the new scopes are NOT added to `local.default_client_scopes`
  — that local is the authoritative scope set for the three existing clients and
  anything listed there is applied to all of them, which would hand the proxy
  clients each other's audience.

## 2. Keycloak: public CLI clients (`tf/deps`)

- [x] 2.1 Add a `freepod_cli_prod` client in
  `tf/deps/keycloak-config/clients.tf` with `access_type = "PUBLIC"`,
  `standard_flow_enabled = true`, `implicit_flow_enabled = false`,
  `direct_access_grants_enabled = false`, `service_accounts_enabled = false`,
  and `pkce_code_challenge_method = "S256"`.
- [x] 2.2 Set its `valid_redirect_uris` to the port-less loopback forms
  `http://127.0.0.1/callback` and `http://localhost/callback`. Comment why the
  port is absent (RFC 8252 §7.3 + Keycloak's `RedirectUtils` loopback
  relaxation, design.md D5) so it is not "fixed" later by adding one.
- [x] 2.3 Enable the device authorization grant on the client. Verify the
  attribute name the `keycloak/keycloak` provider at `~> 5.7.0` expects
  (`oauth2_device_authorization_grant_enabled`); if the pinned version does not
  expose it, set `oauth2.device.authorization.grant.enabled` via `extra_config`
  rather than raising the provider cap — the cap exists for Keycloak 24
  compatibility (`tf/deps/providers.tf`).
- [x] 2.4 Repeat 2.1–2.3 for `freepod_cli_dev`.
- [x] 2.5 Add `keycloak_openid_client_default_scopes` for both CLI clients:
  `acr`, `email`, `profile`, `roles`, `web-origins`, `groups`, plus **only** that
  client's own audience scope. Assert in a comment that the other environment's
  audience scope must never appear here.
- [x] 2.6 `terraform plan` in `tf/deps` and confirm the diff is purely additive
  — no change to the `freepod_prod`, `freepod_dev` or `grafana` clients, and no
  change to the realm.
- [x] 2.7 `terraform apply` in `tf/deps`.

## 3. Verify the authorization server before touching the edge

These run against Keycloak only and are safe while the edge is unchanged.

- [x] 3.1 Confirm both CLI clients exist, are public, and hold no secret:
  `GET /admin/realms/freepod/clients?clientId=freepod-cli-dev`.
- [x] 3.2 Confirm each client carries its own audience scope and not the other's.
- [x] 3.3 Run the device flow end to end against `freepod-cli-dev`: POST to
  `…/protocol/openid-connect/auth/device`, complete the user code in a browser,
  poll the token endpoint, and obtain tokens.
- [x] 3.4 Decode the resulting access token and assert `aud` contains
  `freepod-dev`, plus an `email` claim and a `groups` claim with bare names.
  This is the single most likely thing to be wrong (design.md D3).
- [x] 3.5 Confirm requesting `offline_access` yields a refresh token that still
  works after the 30-minute SSO idle timeout, or verify `typ` is `Offline` on the
  decoded refresh token as a faster proxy for the same property.
- [x] 3.6 Confirm an authorization request omitting `code_challenge` is rejected,
  and that a non-loopback `redirect_uri` is refused.

## 4. Edge: bearer token support (`tf/app`, dev workspace first)

- [x] 4.1 In `tf/app/login/main.tf`, add `"Authorization"` to the `forward-auth`
  middleware's `authRequestHeaders`. Comment that without it the bearer token
  never reaches the verifier and every other setting here is inert.
- [x] 4.2 Add `skip-jwt-bearer-tokens = true` and
  `bearer-token-login-fallback = false` to the oauth2-proxy `extraArgs`.
- [x] 4.3 ~~Add `oidc-extra-audience`~~ — **not needed; deliberately omitted.**
  oauth2-proxy builds its verifier with `Audiences: [clientID] + extra`, so it
  always accepts its own client ID, and the `freepod-api-*` mappers inject
  exactly that ID into `aud`. Setting it would be a no-op that falsely implies
  extra audiences are required — the misreading that leads someone to widen it
  to `account` later. Recorded as a comment in `tf/app/login/main.tf` instead,
  with the `account` prohibition. Verified empirically by task 5.1.
- [x] 4.4 `terraform plan` in the `default` workspace and confirm only the
  oauth2-proxy release and the middleware change.
- [x] 4.5 Apply, and confirm the oauth2-proxy pod reaches Ready. A failure here
  is almost certainly OIDC discovery or a bad audience reference.

## 5. Verify the edge on dev

Dev is group-gated, so it exercises the strictest path (design.md § Risks).

- [x] 5.1 With the token from 3.3, call a protected route on `dev.freepod.eu`
  with `Authorization: Bearer …` and confirm `200`.
- [x] 5.2 Confirm the API resolved the correct user — e.g. `GET /api/me` returns
  the token subject's account, proving `X-Auth-Request-Email` was injected from
  the token's `email` claim.
- [x] 5.3 Confirm a malformed or expired token yields `403`, and that a request
  with no credential yields `401` — the two must differ, since that distinction
  is the whole justification for `bearer-token-login-fallback = false`
  (design.md D6).
- [x] 5.4 Confirm the `401` case leaves the SPA's landing-page behavior
  unchanged.
- [x] 5.5 Confirm a browser session still works end to end — login, an
  authenticated page load, and logout. **Verified manually by the operator
  against dev.freepod.eu after bearer support was enabled.** Not automatable
  here: the session cookie is only obtainable by completing an interactive
  Keycloak login. This is the highest-stakes regression check in the change —
  bearer support must not disturb the browser path — and it passed.
- [x] 5.6 Confirm a token issued to `freepod-cli-prod` is REJECTED by
  `dev.freepod.eu`. This is the environment-isolation property; if it passes,
  the audience configuration is wrong (design.md D2).
- [x] 5.7 Confirm a user outside the `freepod-dev` group is denied on dev even
  with a valid token. **Verified with `fred`** (operator-nominated; member of no
  group). Token obtained without his password via admin impersonation plus the
  normal PKCE authorization-code flow — no credential was set or changed, and
  the resulting session was revoked afterwards (`/logout`, sessions 1 → 0, group
  memberships unchanged).

  Result: fred's token is structurally valid (`aud=['freepod-dev','account']`,
  `azp=freepod-cli-dev`, realm-signed) yet denied, while a member's token
  succeeds — so the gate rejects on authorization, not on token validity.
  Keycloak omits `groups` entirely for a user in no group, so this simultaneously
  verifies the "missing groups claim fails closed" scenario. Denial is `401`,
  not `403`; see design.md D6 for why and why that matters to clients.
- [x] 5.8 **Verify what reaches the API.** Send a bearer-authenticated request
  and inspect the headers the API actually receives (via the `echo` service or
  API request logging) to determine whether Traefik strips the client's raw
  `Authorization` header given that `authResponseHeaders` already lists it. This
  is the one behavior in the change that must be observed rather than reasoned
  about, and it fails silently (design.md § Risks). Record the finding in
  `tf/app/login/main.tf`; if the raw token is forwarded, decide whether to
  accept it or strip it explicitly before proceeding to prod.
- [x] 5.9 Confirm a client-supplied `X-Auth-Request-Email` on an authenticated
  route is overwritten, for both the cookie and bearer paths.
- [x] 5.10 Non-JWT `Authorization` header yields `403` — **confirmed on dev**
  for both `Basic` (`curl -u`) and `Negotiate`, without a cookie present. The
  cookie-plus-header combination was not executed for want of a browser session,
  but it cannot differ: `loadSession` short-circuits only when `scope.Session`
  is already set, and `buildSessionChain` appends the cookie loader *after* the
  JWT loader, so `scope.Session` is nil at JWT-loader time whether or not a
  cookie rides along. The `403` fires before the cookie loader is ever reached.
  Source plus the observed `403` settle it; design.md § Risks stands.

## 6. Roll out to prod

- [x] 6.1 `terraform plan` and apply `tf/app` in the `prod` workspace.
- [x] 6.2 Confirm the oauth2-proxy pod in the `login` namespace reaches Ready.
- [x] 6.3 Repeat 5.1–5.6 against `freepod.eu` with a `freepod-cli-prod` token,
  including the inverse isolation check: a `freepod-cli-dev` token must be
  rejected by prod.
- [x] 6.4 Confirm browser login on `freepod.eu` is unaffected.

## 7. Documentation

- [x] 7.1 Document both flows in `api/README.md` — the loopback + PKCE flow and
  the device flow — with the exact endpoints, the client IDs per environment,
  and a working `curl` transcript for the device flow.
- [x] 7.2 State plainly that a token grants full account authority with no scope
  narrowing, and that Keycloak's account console is the revocation surface
  (design.md § Non-Goals, § Risks).
- [x] 7.3 Note that clients authenticate directly against Keycloak and must not
  use `/oauth2/start`, which mints a browser cookie session rather than tokens.
- [x] 7.4 Extend the `skip_auth_routes` footgun note in `tf/app/login/main.tf`
  to record that skipped routes ignore bearer tokens as completely as cookies.
- [x] 7.5 Update `tf/deps/README.md` and `tf/app/README.md` with the apply
  ordering constraint (`tf/deps` first — design.md D7).

## 8. Close out

- [x] 8.1 Run the API test suite (`cd api && uv run --no-sync pytest`) to
  confirm no application behavior changed. Nothing in `api/` was edited, so this
  is a regression check rather than new coverage. **516 passed, 7 skipped.**
- [x] 8.2 Re-read the delta specs against what was actually built, especially
  the negative assertions in 5.6 and 5.8, and correct any that describe intent
  rather than observed behavior. Four corrections made:
  - The audience requirement implied a separately configured extra audience;
    rewritten to say the allowance derives from oauth2-proxy's own client ID,
    with a scenario asserting no extra audience is configured.
  - Added the device-endpoint PKCE requirement (discovered in 3.3, absent from
    RFC 8628 and from the original spec).
  - Added the `401`-on-authorization-failure scenario to both the client-facing
    and edge specs — the original wrongly implied `403` covered every denial.
  - Recorded that a user in no group has the `groups` claim omitted entirely,
    which is what 5.7 actually exercised.

  Still specified but **not directly exercised**: "the code cannot be redeemed
  without the verifier". PKCE enforcement at the authorization and device
  endpoints was verified; the token-endpoint verifier check was not tested with
  a deliberately mismatched verifier.
- [x] 8.3 Archive the change and sync the delta specs into `openspec/specs/`.
  Done after group 6, so the published specs describe behavior that is actually
  deployed on both environments. Sync applied +17 requirements across four
  capabilities (`oauth2-token-auth` created; `auth-header-integration`,
  `keycloak-user-realm`, `oauth2-proxy-deployment` updated) and all four
  validate `--strict`.

  Pre-existing defect fixed to let this through: the `auth-header-integration`
  main spec carried a non-conformant `## ADDED Requirements` header (main specs
  use `## Requirements`; `ADDED` belongs only in change deltas).
