## Context

Freepod's edge authentication is a Traefik `forwardAuth` middleware
(`tf/app/login/main.tf`) that consults oauth2-proxy at `/oauth2/auth`.
oauth2-proxy runs with `upstream = static://202`, so it is never in the data
path — it is a pure decision oracle that returns `X-Auth-Request-Email` on a 202
and the API (`api/app/deps.py`) trusts that header unconditionally.

Everything below was verified against the live instance at
`keycloak.freepod.eu` rather than inferred from the repository:

- The only realm is `master`, with `registrationAllowed=true`,
  `verifyEmail=true`, `resetPasswordAllowed=true`, SMTP pointed at
  `smtp.purelymail.com`, and `loginTheme`/`emailTheme`/`accountTheme` all set to
  `freepod`.
- Six users, all local passwords, zero federated identities, all emails
  verified.
- Two real clients. `caelus-dev` is confidential, carries redirect URIs for
  **both** `freepod.eu` and `dev.freepod.eu`, has `directAccessGrantsEnabled`
  on, enforces no PKCE, and has default scopes `acr, email, profile, roles,
  web-origins`. `grafana` has the same set **plus `groups`**.
- One group, `freepod-observability`, with a single member. Grafana gates on it
  via `allowed_groups` + `groups_attribute_path` + `role_attribute_strict`.
- The realm's `groups` protocol mapper has `full.path = "false"`, so the claim
  carries bare names (`freepod-observability`), not paths.
- No Keycloak Terraform provider exists anywhere in `tf/`.

Exactly three places in the repository name the realm: `tf/app/login/main.tf`
(lines 72 and 84), `tf/deps/prometheus/grafana.tf` (lines 51-53), and
`ui/.env.production` (line 2).

## Goals / Non-Goals

**Goals:**

- Move end-user authentication off Keycloak's administrative realm onto a
  dedicated `freepod` realm.
- Give each environment its own Keycloak client so a dev session is not
  interchangeable with a prod session.
- Close `dev.freepod.eu` to non-developers without forcing anyone to maintain
  two accounts.
- Replace clickops with Terraform for realm, client, client-scope and group
  configuration.
- Preserve every Freepod application record — deployments, subscriptions, ToS
  acceptances — across the migration.

**Non-Goals:**

- Bearer-token authentication for external API clients. The `freepod-cli`
  public client, PKCE loopback and device flows, oauth2-proxy
  `skip-jwt-bearer-tokens`, adding `Authorization` to the middleware's
  `authRequestHeaders`, and the audience mapper are a deliberate follow-up
  change. This one only lays the per-environment client foundation they need.
- Social identity providers. The archived spec required Google, Apple and
  Microsoft; none were ever built and none are added here.
- Fencing dev's anonymous endpoints. The public catalog reads stay open on dev
  (see Decision 5).
- Guaranteeing password continuity. Carrying hashes over is an optional,
  per-user step during seeding, and the migration completes correctly without it
  (see Decision 4).
- Notifying users. Handled out of band after the migration completes.

## Decisions

### 1. A dedicated `freepod` realm, not a hardened `master`

`master` is Keycloak's administrative realm: its users are the ones that can
hold cross-realm management roles, and public self-registration is currently
open on it. It also cannot be deleted or recreated, which makes it a poor
candidate for configuration management and leaves no clean-slate recovery.

*Alternative considered:* leave users in `master` and simply disable
registration there, admitting new users by invitation. Rejected — it keeps
end-user accounts in the administrative realm permanently, and Freepod is a
public service where open registration is a product requirement.

### 2. Manage the realm as a Terraform resource, guarded by `prevent_destroy`

A `keycloak_realm` **resource** rather than a `data` source, with
`lifecycle { prevent_destroy = true }`.

The general safety argument favors a `data` source: Terraform then has no code
path by which a corrupted state file or a mistaken `terraform destroy` can
delete a realm, and deleting a realm cascades to every user, credential and
session inside it. That argument is decisive when *adopting an existing realm
full of users*.

It is the wrong trade here. The realm is greenfield, and the entire point of the
change is to get SMTP settings, themes, and registration policy out of clickops
and into code — which a `data` source cannot do. `prevent_destroy` converts the
destructive plan into a hard error, which covers the risk once users land in it.

*What Terraform does not manage:* users. The provider offers a `keycloak_user`
resource; it is not used for end users. Users live in Keycloak's own Postgres
and Terraform never enumerates them.

`prevent_destroy` alone is **not** sufficient. It is a Terraform-side lifecycle
guard that only applies while the resource block is present in the
configuration: delete the block and apply, and Terraform plans a destroy with no
guard to trip. The realm therefore also sets the provider-side
`terraform_deletion_protection = true`, which is enforced inside the provider's
delete call and so survives removal of the block from code. The two together —
one guarding the plan, one guarding the API call — are what close the path from
`terraform apply` to user data loss.

### 3. Realm and clients in `tf/deps`, client selection in `tf/app`

Keycloak realm configuration is genuinely a singleton: one Keycloak instance
serves both environments. `tf/deps` is the existing home for shared singleton
dependencies and has no workspaces, so both clients are declared there as two
plain resources — not one resource parameterized by workspace. `tf/app`, which
*is* workspaced, selects which client ID and secret to use.

Client secrets stay in the existing manual `secrets.auto.tfvars` files rather
than being wired between root modules with `terraform_remote_state`. That keeps
the two root modules decoupled and matches current practice.

This forces one shape change. Terraform loads `*.auto.tfvars` for **every**
workspace, so the scalar `var.oauth2_proxy_client_secret` cannot hold two
different values. It becomes a map keyed by workspace:

```hcl
variable "oauth2_proxy_client_secrets" {
  type      = map(string)   # { default = "...", prod = "..." }
  sensitive = true
}
# consumed as: var.oauth2_proxy_client_secrets[terraform.workspace]
```

**The dev workspace is named `default`, not `dev`** — `terraform.tfstate.d/`
contains only `prod`. The map keys must follow the existing
`local.is_prod_workspace` convention rather than inventing a `dev` key that
would never match.

### 4. Seed accounts credential-less, with optional per-user hash carry-over

The baseline is that accounts are seeded with `emailVerified: true`,
`enabled: true`, and **no credentials**, and users obtain a password through the
existing self-service reset flow, which the realm already supports
(`resetPasswordAllowed=true`, `resetCredentialsFlow="reset credentials"`, live
SMTP) and which does not require a pre-existing credential. This path always
works and requires nothing beyond the admin REST API.

Carrying the existing password hashes over is an **optional enhancement applied
per user during seeding**, gated on verifying one account first. It is optional
because the baseline is sufficient for six people; it is worth doing because it
removes a shared failure mode (below).

**Hashes are portable.** The `credential` table has no realm column — its only
realm binding is transitive, through `user_entity.realm_id`. Keycloak applies no
realm-level pepper, so a stored credential is a self-contained PBKDF2 record:
`secret_data` holds `{value, salt, additionalParameters}` and `credential_data`
holds `{hashIterations: 210000, algorithm: "pbkdf2-sha512"}`. All six accounts
use this modern format, with the legacy `salt` column NULL.

**Nothing else is attached.** Every table referencing a user was counted:
`user_attribute` 0, `user_required_action` 0, `federated_identity` 0,
`user_consent` 0, non-password credentials 0 (no OTP, no WebAuthn). Only one
group membership and eight role mappings exist. The role mappings are
`default-roles-master` — auto-assigned in the new realm, so not migrated — and
`admin` on two accounts. **Role mappings are deliberately dropped**, because an
end-user account holding the `master` realm's `admin` role is precisely the
privilege concern motivating this migration; changing realms cleans it up.

**Why it belongs in seeding and not at the end.** The value of a migrated hash
is that the user never has to reset. Users hit an unusable login within minutes
of cutover and reset immediately, so by the end of the soak period every account
has been reset and the hashes are worthless — migrating them then would silently
overwrite each user's newly chosen password with their old one. The window is
open only during seeding.

**Why the admin API and not direct SQL.** Keycloak 24 runs a local Infinispan
`users` cache (`conf/cache-ispn.xml`; no override in `keycloak.conf`), so writes
made directly to Postgres are not reliably visible to the running server. A
credential-less user also has *no* `credential` row, making it an `INSERT` of
six hand-assembled columns rather than an `UPDATE`. Going through
`POST /admin/realms/freepod/users` with a `credentials` array handles cache
invalidation and needs no schema knowledge.

**One assumption to verify rather than trust.** The admin API redacts
`secretData` on read, so the write path cannot be proven to round-trip without
doing it. Seeding one user with credentials and confirming they can sign in with
their existing password is the gate; if it fails, drop credentials and fall back
to the baseline with nothing lost.

**`requiredActions: ["UPDATE_PASSWORD"]` is deliberately NOT set** on
credential-less accounts. Required actions are a post-authentication interrupt,
evaluated *after* the credential is validated. A user with no credential can
never get past the login form, so the action would never fire and the account
would simply be locked out.

*Alternative considered:* seed a temporary password with `temporary: true`,
which auto-adds `UPDATE_PASSWORD` and forces a change on first login. Rejected —
it replaces one self-service email with six secrets that have to be transmitted
out of band, which is strictly worse.

`emailVerified: true` is both accurate (all six are verified in `master`) and
necessary: with `verifyEmail=true` on the realm, seeding them unverified would
add a `VERIFY_EMAIL` round trip before anyone could reset a password.

### 5. Close dev by authorization, not registration

`registrationAllowed` is a **realm-level** setting in Keycloak with no
per-client equivalent. With one shared realm — which is required, because users
must not need two accounts — "open on prod, closed on dev" is not expressible as
a registration setting at all.

The separation is therefore:

- **Authentication is shared.** One realm, one user database, one signup. A user
  who registers on prod is the same principal on dev.
- **Authorization is per-environment.** Dev additionally requires membership of
  the `freepod-dev` group, enforced at the edge by oauth2-proxy
  `allowed_groups`, set only in the non-prod workspace.

This mirrors the proven `freepod-observability` pattern already gating Grafana.
The delta that makes it possible for Freepod is the `groups` client scope, which
is assigned to the `grafana` client but not to `caelus-dev` — which is why the
claim never reaches oauth2-proxy today.

**`groups` is not a Keycloak built-in.** Keycloak 24's
`OIDCLoginProtocolFactory` creates exactly `profile`, `email`, `address`,
`phone`, `roles`, `web-origins`, `microprofile-jwt` and `acr`, plus
`offline_access` and the SAML `role_list` — ten scopes, and `groups` is not
among them. The one in `master` was created by hand when Grafana was set up,
which is also why `caelus-dev` (created earlier) lacks it while `grafana`
(created later) has it. A freshly created `freepod` realm has no `groups` scope
at all, so the scope **and** its `oidc-group-membership-mapper` must be declared
in Terraform, not merely referenced and attached.

Two details govern correctness:

- **Bare names, not paths.** The realm's `groups` mapper has
  `full.path = "false"`, so `allowed_groups` takes `freepod-dev`, not
  `/freepod-dev`.
- **Enforced on every request.** oauth2-proxy's `getAuthenticatedSession` calls
  `provider.Authorize()` on each request and `authOnlyAuthorize` applies
  `checkAllowedGroups` on the AuthOnly endpoint that `forwardAuth` hits, clearing
  the session cookie on denial. Group removal takes effect on the next request,
  not at token expiry.

**Accepted limitation:** `IsAllowedRequest()` returns early *before* the
authorization check, so `skip_auth_routes` bypass group gating entirely. Dev's
anonymous product catalog, plans, hostname validators and OpenAPI docs stay
publicly readable regardless of group membership. This is accepted — those
endpoints expose no tenant data, and fencing them would break the dev SPA's
landing page and live deploy validators.

*Alternative considered:* oauth2-proxy's `--allowed-role`, which reads
`realm_access.roles` and `resource_access.*.roles`. A client role would be more
precisely scoped than a realm group, but groups match the existing Grafana
precedent and are easier to administer.

### 6. Split `caelus-dev` into per-environment clients

One client currently answers for both hosts, holding all four redirect URIs and
one secret shared across both Terraform workspaces. Group gating would still
function — `allowed_groups` is a per-proxy-instance flag — but the isolation
would rest entirely on that flag with nothing at the IdP behind it, and tokens
would carry no signal distinguishing the environments.

`freepod-prod` and `freepod-dev` each hold only their own host's redirect URIs
and their own secret. Both get PKCE `S256` required and
`directAccessGrantsEnabled` off; neither is needed by the browser flow, and the
direct access grant trades a username and password straight for tokens.

This also matters for the deferred token work: audience-based validation is what
will let the edge say "this token is for dev", and that is impossible while both
environments answer to one `aud`.

### 7. Cut over dev first

The issuer change is a hard cutover — existing `_oauth2_proxy` cookies become
worthless the moment it lands, and oauth2-proxy fails OIDC discovery at startup
if pointed at a realm that does not exist. Creating the realm and clients is
fully additive and can be applied and iterated on with nothing referencing it.
Only once dev is verified does prod follow.

## Risks / Trade-offs

**Repointing oauth2-proxy before the realm exists takes down both environments**
→ Terraform must create the realm and clients (Phase 1) and be verified before
any change to `tf/app/login/main.tf` (Phase 3). The phases are ordered so the
additive work is fully applied and the discovery document is reachable first.

**The UI carries the realm name in a build-time constant** →
`ui/.env.production` is inlined by Vite at build time, so no Terraform apply can
change it; the migration requires a UI rebuild and image republish. Not
outage-causing — `master` still exists after cutover, so a stale account link
resolves, it just shows an empty account page — but it is wrong from the moment
prod cuts over, so it belongs in the same phase. The same variable doubles as
the proxy-auth feature flag in `AuthContext.tsx` and `useStartSignup.tsx`, so it
must stay set and non-empty or the SPA falls back to local-dev email-dialog
auth.

**Forgetting Grafana strands the observability login** →
`tf/deps/prometheus/grafana.tf` points at `realms/master`, and the
`freepod-observability` group with its membership lives there. If users move and
Grafana does not, Grafana access is lost — or it requires exactly the dual
account this design avoids. The `grafana` client, the group, and the membership
all migrate together in Phase 5.

**A fresh realm silently loses SMTP and theming** → With no SMTP, `verifyEmail`
and the password reset flow both break quietly, which is precisely the flow the
migrated users depend on. Themes are set on the realm resource; SMTP needs the
care described immediately below. Phase 1 verification includes sending a test
email before any user is seeded.

**The `smtp_*` Terraform variables are not Keycloak's SMTP credentials** → The
`smtp_host` / `smtp_port` / `smtp_username` / `smtp_password` variables in
`tf/deps/secrets.auto.tfvars` are consumed by `module "mailer"` alone, where
they become `RELAY_*` settings for an OpenSMTPD relay that forwards to
`smtp.purelymail.com:587` as `noreply@freepod.eu`. Keycloak's `master` realm
does **not** use that relay: it dials `smtp.purelymail.com:465` directly with
`ssl=true`, `starttls=false`, as a *different* mailbox account
(`caelus@deprutser.be`), with `from`/`replyTo` of `noreply@freepod.eu`. Wiring
the realm from the `smtp_*` variables therefore produces a configuration that
has never been exercised for Keycloak — a different port, a different transport
and a different account — and it is the one flow every credential-less user
depends on. Three coherent resolutions were considered, in order of preference;
**option 1 was chosen** and is what `tf/deps/keycloak-config/realm.tf`
implements. The module deliberately does not accept the root module's `smtp_*`
variables at all, so the wrong credentials cannot be wired in by reflex.

1. **Point the realm at the in-cluster relay**
   (`smtp.mailer.svc.cluster.local:25`, `auth=false`, no TLS, `from` and
   `replyTo` `noreply@freepod.eu`). This is already the house pattern —
   Alertmanager sends this way (`tf/deps/prometheus/prometheus.tf`) — it keeps
   upstream credentials out of the realm configuration entirely, and the relay
   is what the `smtp_*` variables were provisioned for.
2. **Replicate `master` exactly** (purelymail:465, `ssl=true`,
   `caelus@deprutser.be`). Known-working, but requires introducing a new
   variable for that account's password, which currently exists only inside the
   live realm.
3. **Keep purelymail:587 as `noreply@freepod.eu`.** Plausible, but unproven for
   Keycloak, and it silently changes the sending account.

The Phase 2 test email remains the gate, and it must pass before any account is
seeded credential-less. Note that option 1 puts the relay on the critical path:
if `module.mailer` is not running, realm email fails. That is the same exposure
Alertmanager already accepts, and it trades an untested external mail path for a
tested internal one.

**Requiring PKCE at Keycloak without enabling it in oauth2-proxy breaks every
login** → Setting `pkce_code_challenge_method = "S256"` on a client makes PKCE
*mandatory*, and oauth2-proxy sends a code challenge only when
`--code-challenge-method` is set. With one side configured and not the other,
Keycloak rejects every authorization request with
`error=invalid_request, Missing parameter: code_challenge_method`. This failed
silently in the worst way during the dev cutover: oauth2-proxy logged a warning,
started anyway and passed its readiness probe, so the pod looked healthy while
authentication was completely broken. **Pod-Ready does not mean login works.**
The client attribute and the proxy flag are a matched pair and must move
together — the same coupling as Grafana's `use_pkce` (Decision 6 note), just in
the opposite direction. Verify against the authorization endpoint directly: a
request without a challenge should not 302 with that error.

**Group gating fails closed if the `groups` claim is missing or path-formatted**
→ The claim is absent from `caelus-dev` today, and a `full.path=true` mapper
would emit `/freepod-dev` where `allowed_groups` expects `freepod-dev`. Both
clients get `groups` as a default scope, and Phase 3 verification explicitly
tests a member login *and* a non-member rejection rather than assuming.

**All users are logged out at cutover** → Accepted and expected. Session
invalidation is inherent to changing the issuer.

**Seeding credential-less makes new-realm SMTP a single point of failure for all
access** → If SMTP on `freepod` is subtly wrong — a rejected from-address, a
deliverability problem, a typo'd credential — then no user can obtain a password
and everyone is locked out simultaneously, including the operator. Two
mitigations, in order of strength: carrying password hashes over during seeding
(Decision 4) demotes broken SMTP to an annoyance discovered later; and Phase 1
verifies the reset flow end to end before any user depends on it. Self-service
reset remains available per user regardless of whether their hash was carried.

**A carried-over hash silently reverts a password the user has already changed**
→ Only possible if hash migration runs after users have started resetting, which
is why it is confined to the seeding phase and explicitly not deferred. Once
cutover has happened, the optional step is closed.

**A state-file mishap could target the realm for replacement** →
`prevent_destroy` on the `keycloak_realm` resource turns any such plan into a
hard error rather than a cascading delete of every user and credential.

## Migration Plan

**Phase 0 — Prep.** Add the `keycloak/keycloak` provider to `tf/deps`
(`mrparkers/keycloak` is unmaintained since January 2024). Capture rollback
artifacts: a `partial-export` of `master` and a `pg_dump` of the Keycloak
database.

*Corrected during implementation:* the provider is pinned `~> 5.7.0`, **not**
5.9.0 as originally written. From 5.8.0 the provider unconditionally sends
`bruteForceStrategy` in the realm representation — a field added in Keycloak 26.
We run Keycloak **24.0.5**, whose deserializer rejects the entire request with
`400 {"errorMessage":"unable to read contents from stream"}`, so realm creation
fails outright on 5.8.0 and 5.9.0. Established by bisecting the provider's
captured request body against the live admin API: the full body 400s, the same
body minus that one field 201s. 5.7.0 was then verified end to end by creating
and destroying a throwaway realm.

The only casualty is `add_to_token_introspection` on the group membership
mapper, which does not exist before 5.8.0; it is omitted, leaving
`introspection.token.claim` unset where `master` has it `"true"`. Inert here —
nothing reads the groups claim through introspection. Raising the cap requires
upgrading Keycloak to 26.x, which is its own change.

**Phase 1 — Create, additive.** Realm `freepod` with SMTP (see the SMTP risk
above — *not* straight from the `smtp_*` variables), themes,
`registrationAllowed=true`, `verifyEmail=true`, `prevent_destroy` **and**
`terraform_deletion_protection`. The `groups` client scope and its
group-membership mapper, declared rather than referenced. Clients
`freepod-prod`, `freepod-dev`, `grafana` — per-host redirect URIs only, `groups`
attached as a default scope, direct access grants off. PKCE `S256` on
`freepod-prod` and `freepod-dev` only; **not** on `grafana`, which would break
its login until `use_pkce` is set on the Grafana side as a matched pair. Groups
`freepod-dev` and `freepod-observability`. Nothing references any of it yet, so
this is safe to apply and iterate. Verify the discovery document resolves and a
test email sends.

**Phase 2 — Seed users.** Create the accounts via admin REST with
`emailVerified: true`, `enabled: true`, and no required actions. Optionally
carry password hashes over per user, gated on seeding one account with its
credential and confirming it can sign in; on failure, drop credentials and
proceed with the credential-less baseline. Role mappings are not migrated. Add
the appropriate member to `freepod-dev` and `freepod-observability`.

**Phase 3 — Cut over dev.** Update `tf/app/login/main.tf` (issuer, backend
logout URL, client ID/secret from the map) and set
`allowed_groups = ["freepod-dev"]` for the non-prod workspace. Apply to the
`default` workspace. Verify: a group member can log in; a non-member is
rejected; anonymous catalog reads still succeed.

**Phase 4 — Cut over prod.** Same apply in the `prod` workspace, without
`allowed_groups`. All sessions invalidate at this point.

**Phase 5 — Grafana and UI.** Repoint Grafana's three OIDC URLs. Rebuild and
republish the UI image with the updated `VITE_KEYCLOAK_ACCOUNT_URL`.

**Phase 6 — Cleanup, after soak.** Disable registration on `master`, delete the
`caelus-dev` client, delete the five migrated users. The `admin` account stays —
it is the Keycloak instance administrator and must live in `master`.

**Rollback.** `master` is left fully intact through the soak period, *including
its original password hashes*. Reverting is: revert the Terraform change,
rebuild the UI, and users log in with their existing credentials. No data
reconstruction is required, which is what keeps this cutover low-stakes.

**Why the application needs no changes.** `api/app/models/core.py` stores only
`email` on `UserORM`, behind a unique index on `lower(email)` where
`deleted_at is null`, and `api/app/deps.py` resolves the caller by that column.
No Keycloak subject identifier is persisted anywhere in Freepod. Keycloak
identity can be rebuilt underneath the application without touching a single
row, so deployments, subscriptions and ToS acceptances stay attached by email
alone. `UserORM.is_admin` is likewise Freepod-side only, and dev and prod have
separate Postgres databases — nothing to migrate.

*Correction found during the prod cutover:* the claim that no Keycloak subject
identifier is persisted is **not quite true of existing data**. The prod
database contains two `UserORM` rows whose `email` column holds a `master`
realm **user id** rather than an address —
`f0c6de07-c4e0-4fd5-8cfe-fd32e41e66ef` (erik) and
`4c968972-27ad-42a1-988e-c3f1b66494eb` (erik2) — auto-created by
`get_current_user` during a period when the proxy passed `sub` rather than the
email claim. They are inert: both own zero deployments and zero subscriptions,
so nothing is orphaned by the cutover, and affected users simply resolve to
their real-email rows from now on. Worth deleting as unrelated tidy-up; not
done here because it is outside this change.

*Corollary worth recording:* because email is the sole join key, the email claim
is security-critical. An account whose email could be changed to another user's
would take over that Freepod account. The realm's `verifyEmail=true` is what
guards this, and it is a reason not to relax that setting later.

## Open Questions

None blocking. Two items are deliberately deferred rather than unresolved: the
follow-up change for OAuth2 bearer-token support, and whether social identity
providers are ever wanted (removed from the spec here rather than left as a
dormant requirement, since an unbuilt requirement sitting in a spec is how the
`master`-realm drift went unnoticed in the first place).
