## Why

Freepod has no way to authenticate a request that did not come from a browser.
Every protected route sits behind a Traefik `forwardAuth` middleware that asks
oauth2-proxy for a decision, and oauth2-proxy is given exactly one input: the
`Cookie` header (`tf/app/login/main.tf`, `authRequestHeaders`). An API client
holding a perfectly valid Keycloak access token cannot present it — the token is
dropped at the edge before oauth2-proxy ever sees it.

The practical consequence is that there is no supported way to build an external
integration. The existing `caelus` CLI is not a counterexample: it imports
`api/app/services/` and talks to the database directly, using `--as-user` /
`CAELUS_USER_EMAIL` as an asserted identity. That is an operator tool that must
run next to the database, with no authentication at all. Anything tenant-facing
and remote needs a real credential.

The foundation for this already exists and is idle. The `freepod` realm
advertises `urn:ietf:params:oauth:grant-type:device_code` and PKCE `S256`;
`offline_access` is available as an optional client scope; offline sessions idle
out after 30 days with no maximum lifespan, which is exactly the shape a stored
CLI credential wants. The running oauth2-proxy (v7.14.2) ships
`--skip-jwt-bearer-tokens`, which verifies a bearer JWT against the OIDC issuer
and synthesizes a session from its claims, so `--set-xauthrequest` keeps emitting
`X-Auth-Request-Email` exactly as it does for a cookie session. The
`2026-08-10-migrate-keycloak-freepod-realm` change deferred this work by name and
built the per-environment clients it depends on.

## What Changes

- Add a **public** Keycloak client per environment — `freepod-cli-prod` and
  `freepod-cli-dev` — holding no client secret, because a distributed CLI cannot
  keep one. Each requires PKCE `S256`, enables the OAuth 2.0 Device
  Authorization Grant, and registers loopback redirect URIs in their port-less
  form so an ephemeral local port matches.
- Add a matching audience client scope per environment (`freepod-api-prod`,
  `freepod-api-dev`) carrying an audience protocol mapper that injects that
  environment's oauth2-proxy client ID into the `aud` claim. Keycloak's default
  access token carries `aud: ["account"]` and puts the requesting client in
  `azp`, which oauth2-proxy's audience verification rejects. This mapper is the
  supported fix; widening `--oidc-extra-audience` to `account` instead would
  make every token in the realm a valid Freepod credential and is explicitly
  rejected in design.md.

  The pairing is not symmetry for its own sake. `keycloak-user-realm` requires
  that a token issued for one environment not be usable on the other, and since
  both CLI clients register identical loopback redirect URIs, the `aud` claim is
  the *only* thing that separates them. A single realm-wide CLI client would
  have to inject both audiences and would break that invariant.
- Enable bearer-token verification on oauth2-proxy via
  `--skip-jwt-bearer-tokens`, with `--bearer-token-login-fallback=false` so an
  expired or invalid token yields `403` rather than an HTML login redirect that
  is useless to a non-browser client.
- Add `Authorization` to the Traefik `forward-auth` middleware's
  `authRequestHeaders`, so a bearer token reaches oauth2-proxy at all. Without
  this one line every other part of this change is inert.
- Give both CLI clients the `groups` client scope, so bearer clients carry the
  claim that `allowed_groups` gates `dev.freepod.eu` on. Omitting it fails dev
  authentication closed.
- Document the two supported client flows — authorization code with PKCE over a
  loopback redirect for interactive use, device authorization grant for headless
  and remote use — including the requirement that a client authenticates
  **directly against Keycloak**, not through oauth2-proxy's `/oauth2/start`,
  which exists only to mint a browser cookie session.

No API changes. `api/app/deps.py` continues to read `X-Auth-Request-Email` and
resolve callers by `lower(email)`, unaware that a token was involved. Keeping
token handling entirely at the edge is the point of the design, not an oversight.

Explicitly out of scope, deferred to a follow-up change: the CLI application
itself — the loopback listener, device-flow polling, credential storage, and
token refresh. This change delivers the authorization server and edge
configuration such a client would target, and is independently verifiable with
`curl`.

Also deliberately not addressed here, and recorded in design.md as accepted
risk: token scoping (a bearer token grants exactly what a browser session
grants, because the API has no notion of OAuth scopes) and refresh-token
rotation (the realm sets `revokeRefreshToken = false`, which is a realm-wide
setting that would change browser session behavior too).

## Capabilities

### New Capabilities

- `oauth2-token-auth`: token-based authentication for non-browser API clients.
  Covers the per-environment public CLI clients and their grants, the audience
  client scopes that make a Keycloak access token verifiable by oauth2-proxy,
  the two supported client flows and their redirect-URI rules, and the error
  contract a client can rely on for expired, invalid and
  insufficiently-privileged tokens.

### Modified Capabilities

- `oauth2-proxy-deployment`: adds bearer-token verification to oauth2-proxy's
  required configuration — `skip-jwt-bearer-tokens`, the audience allowance, and
  `bearer-token-login-fallback=false` — and states that group gating on
  `dev.freepod.eu` applies to bearer clients on the same terms as cookie
  sessions.
- `auth-header-integration`: the `forward-auth` middleware must forward the
  `Authorization` request header, and `X-Auth-Request-Email` is now derived from
  either a cookie session or a verified bearer token. Adds the requirement that
  a client-supplied `X-Auth-Request-Email` is never trusted on a bearer-
  authenticated route.
- `keycloak-user-realm`: adds the per-environment public CLI clients and their
  audience client scopes to the realm's declared client and client-scope
  inventory, alongside the existing `freepod-prod`, `freepod-dev` and `grafana`
  clients, and states that the existing one-client-per-environment invariant
  extends to them.

## Impact

**Terraform.** `tf/deps/keycloak-config/clients.tf` gains the two CLI clients;
`tf/deps/keycloak-config/scopes.tf` gains the two audience scopes and their
mappers. `tf/app/login/main.tf` changes in two places: three new `extraArgs`
entries on the oauth2-proxy Helm release, and one new entry in the
`forward-auth` middleware's `authRequestHeaders`.

Both root modules are involved and the ordering matters: `tf/deps` must be
applied first, because oauth2-proxy fails its readiness probe if the audience it
is told to accept does not yet exist as a realm scope.

**Keycloak.** Two new clients and two new client scopes in the `freepod` realm.
No realm-level settings change, so no existing session is invalidated and no
user action is required.

**API.** None. Verified: `api/app/deps.py` reads only `X-Auth-Request-Email`, and
no endpoint inspects `Authorization`.

**Security posture.** Bearer tokens become a second path to an authenticated
session, so the `skip_auth_routes` list keeps its existing footgun — routes on
that list bypass oauth2-proxy entirely and therefore ignore a bearer token as
completely as they ignore a cookie. Offline tokens issued to `freepod-cli` are
long-lived by realm policy (30-day idle, no maximum), and Freepod itself offers
no revocation UI; Keycloak's account console is the revocation surface.
