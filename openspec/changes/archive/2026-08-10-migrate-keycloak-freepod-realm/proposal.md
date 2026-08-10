## Why

Freepod authenticates its end users against Keycloak's built-in `master` realm —
the administrative realm that governs the entire Keycloak instance — with public
self-registration enabled. This was never a decision: the archived
`keycloak-user-realm` spec called for a dedicated realm, but Keycloak bootstraps
with only `master`, the bootstrap admin lands there, and the first working client
was created in the realm the operator was already standing in. The issuer URL was
hardcoded and never revisited.

The consequences are real but still cheap to undo. Anyone on the internet can
self-register into the realm whose users can hold cross-realm management roles;
`master` can never be deleted or recreated, so it is the worst possible realm to
bring under configuration management; and a single Keycloak client
(`caelus-dev`) serves both `freepod.eu` and `dev.freepod.eu`, so a session minted
for dev is indistinguishable from one minted for prod. Meanwhile all realm
configuration is clickops — no Keycloak provider exists anywhere in `tf/`.

There are six user accounts, all local passwords, zero federated identities. This
migration will never be cheaper than it is now, and upcoming work on OAuth2 token
authentication for external API clients needs per-environment clients as its
foundation.

## What Changes

- Create a dedicated `freepod` realm, managed as Terraform code
  (`keycloak/keycloak`, pinned `~> 5.7.0` for Keycloak 24 compatibility — see
  design.md Phase 0) in `tf/deps`, carrying the SMTP settings, the
  `freepod` login/email/account themes, open self-registration, and email
  verification that `master` holds today.
- **BREAKING**: replace the shared `caelus-dev` client with two per-environment
  clients, `freepod-prod` and `freepod-dev`, each holding only its own host's
  redirect URIs, with PKCE `S256` required and direct access grants disabled.
- Add `groups` as a default client scope on both clients, so the `groups` claim
  reaches oauth2-proxy. It is absent from `caelus-dev` today, which is why
  group-based gating is not currently available to Freepod.
- Gate `dev.freepod.eu` on membership of a new `freepod-dev` Keycloak group via
  oauth2-proxy `allowed_groups`, applied to the non-prod workspace only. Public
  self-registration stays open on the shared realm — dev is closed by
  *authorization*, not by registration, so nobody needs two accounts.
- **BREAKING**: `var.oauth2_proxy_client_secret` becomes a map keyed by
  Terraform workspace. `secrets.auto.tfvars` is auto-loaded for every workspace,
  so a scalar cannot express two per-environment client secrets.
- Move the `grafana` client and the `freepod-observability` group into the
  `freepod` realm, and repoint Grafana's three OIDC endpoint URLs.
- Seed the five end-user accounts into `freepod` with a verified email, enabled
  status, and no role mappings — dropping in particular the `master` realm
  `admin` role that two end-user accounts hold today. Baseline is that users set
  a password through the existing self-service reset flow; carrying their
  existing password hashes over is an optional, per-user step during seeding,
  gated on verifying one account first.
- Retain `master` intact through a soak period as the rollback path, then
  disable registration on it and remove the migrated users and the `caelus-dev`
  client. The `admin` account stays — it is the Keycloak instance
  administrator.

Explicitly out of scope, deferred to a follow-up change: the `freepod-cli`
public client, PKCE loopback and device flows, oauth2-proxy
`skip-jwt-bearer-tokens`, and bearer-token support at the Traefik edge. This
change establishes only the realm and per-environment clients that work depends
on.

## Capabilities

### New Capabilities
- `keycloak-terraform-config`: Keycloak realm, client, client-scope and group
  configuration declared as Terraform in `tf/deps`, including the realm
  destroy-protection guard and the division of responsibility between the
  singleton `tf/deps` root module and the workspaced `tf/app` root module.

### Modified Capabilities
- `keycloak-user-realm`: rewritten to describe the `freepod` realm rather than
  the `caelus` realm that was never built. The Google, Apple and Microsoft
  identity-provider requirements are removed — they were never implemented and
  are not planned here. Adds the two per-environment clients, the `groups`
  client scope, and the `freepod-dev` / `freepod-observability` groups.
- `oauth2-proxy-deployment`: issuer and backend-logout URLs move to the
  `freepod` realm; the client ID and secret become per-workspace; adds the
  dev-only `allowed_groups` gating requirement.
- `logout-infrastructure`: the documented backend-logout URL moves to the
  `freepod` realm (and drops a stale `keycloak.app.deprutser.be` hostname).
- `monitoring-dashboards-access`: Grafana's OIDC endpoints and the
  `freepod-observability` group move to the `freepod` realm.

## Impact

**Terraform.** `tf/deps` gains the `keycloak/keycloak` provider and a new
Keycloak configuration module. `tf/app/login/main.tf` changes issuer, logout URL,
client ID/secret, and gains `allowed_groups`. `tf/app/variables.tf` and both
`secrets.auto.tfvars` files change shape. `tf/deps/prometheus/grafana.tf` changes
three URLs.

**UI.** `ui/.env.production` hardcodes the realm in
`VITE_KEYCLOAK_ACCOUNT_URL`. Vite inlines `import.meta.env` at build time, so
this requires a UI rebuild and image republish — a Terraform apply alone will not
change it. The same variable doubles as the proxy-auth feature flag read by
`ui/src/state/AuthContext.tsx` and
`ui/src/components/landing/useStartSignup.tsx`, so it must remain set and
non-empty.

**API.** None. `UserORM` stores only `email` and `deps.py` resolves callers by
`lower(email)`; no Keycloak subject identifier is persisted anywhere, so Keycloak
identity can be rebuilt underneath Freepod without touching a single application
row.

**Users.** All sessions are invalidated at cutover, and each of the six accounts
needs a one-time password reset through the existing self-service flow. Notifying
users is handled out of band and is not part of this change.
