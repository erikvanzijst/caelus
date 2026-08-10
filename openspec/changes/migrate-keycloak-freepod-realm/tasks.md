## 1. Phase 0 — Provider and rollback artifacts

- [x] 1.1 Add the `keycloak/keycloak` provider (pinned `~> 5.7.0`) to
      `tf/deps/providers.tf`, configured against `https://keycloak.freepod.eu`
      using the existing `keycloak_admin_password` variable
- [x] 1.2 Add a `keycloak_url` variable (or local) so the admin endpoint is not
      hardcoded across resources
- [x] 1.3 Run `terraform init` in `tf/deps` and confirm the provider downloads
      and authenticates against the live instance
- [x] 1.4 Capture a `partial-export` of the `master` realm
      (`exportGroupsAndRoles=true&exportClients=true`) into `var/` as a rollback
      artifact
- [x] 1.5 Capture a `pg_dump` of the Keycloak Postgres database as a rollback
      artifact and record where it is stored
- [x] 1.6 Record the six existing accounts (username, email, emailVerified,
      enabled) for use in Phase 3 seeding

## 2. Phase 1 — Terraform: realm, clients, groups

- [x] 2.1 Create a `tf/deps/keycloak-config/` module for realm and client
      configuration, separate from the existing `tf/deps/keycloak/` deployment
      module
- [x] 2.2 Declare the `keycloak_realm` resource for `freepod` with
      `registrationAllowed = true`, `verifyEmail = true`,
      `resetPasswordAllowed = true`, and
      `lifecycle { prevent_destroy = true }`
- [x] 2.3 Point the realm's SMTP server block at the in-cluster mailer relay
      (`smtp.mailer.svc.cluster.local:25`, no auth, no TLS on that hop,
      From/Reply-To `noreply@freepod.eu`).
      **Corrected during implementation** (decided by Erik): the original task
      said to wire this from the `smtp_host`/`smtp_port`/`smtp_username`/
      `smtp_password` variables in `tf/deps/secrets.auto.tfvars`. Those are not
      Keycloak's SMTP credentials — `tf/deps/main.tf` passes them only to
      `module.mailer`, where they become the `wodby/opensmtpd` relay's
      *upstream* purelymail credentials. Using them here would have given the
      realm an untested mail path (purelymail:587 as `noreply@freepod.eu`),
      differing from `master`'s live config (purelymail:465, `ssl=true`, as
      `caelus@deprutser.be`) in port, transport and mailbox account. Sending
      through the relay is the established house pattern — Alertmanager already
      does it (`tf/deps/prometheus/prometheus.tf:22`) — keeps upstream
      credentials out of the realm config, and needs no new secret
- [x] 2.4 Set `login_theme`, `email_theme` and `account_theme` to `freepod` on
      the realm
- [x] 2.5 Declare the `freepod-prod` client: confidential, standard flow on,
      `direct_access_grants_enabled = false`, PKCE `S256`, redirect URIs for
      `freepod.eu` only, web origins for `freepod.eu` only
- [x] 2.6 Declare the `freepod-dev` client with the same settings but redirect
      URIs and web origins for `dev.freepod.eu` only
- [x] 2.7 Declare the `grafana` client with redirect URI
      `https://grafana.freepod.eu/login/generic_oauth`
- [x] 2.8 Create the `groups` client scope with an
      `oidc-group-membership-mapper` (`full.path = false`) and attach it as a
      **default** client scope on all three clients (this is the delta that
      makes group gating possible; `caelus-dev` lacks it today).
      **Corrected during implementation**: `groups` is NOT a Keycloak built-in.
      Keycloak 24.0.5 ships ten default client scopes and `groups` is not among
      them — the one in `master` was created by hand when Grafana was set up.
      A fresh realm has nothing to attach, so the scope and its mapper must be
      declared, not merely referenced
- [x] 2.9 Declare the `freepod-dev` and `freepod-observability` groups
- [x] 2.10 Add module outputs for the three client IDs and secrets
- [x] 2.11 Run `terraform apply` in `tf/deps` and confirm the plan is purely
      additive — no changes to existing `master` resources. Applied:
      `11 added, 0 changed, 0 destroyed`, all 33 pre-existing resources no-op.
      Verified afterwards that `master`'s `caelus-dev` and `grafana` clients
      are byte-identical to the Phase 0 export. Keycloak auto-created a
      `freepod-realm` management client inside `master` as a side effect of
      realm creation — expected, Keycloak-owned, not Terraform-managed

## 3. Phase 2 — Verify the new realm before it carries traffic

- [x] 3.1 Confirm
      `https://keycloak.freepod.eu/realms/freepod/.well-known/openid-configuration`
      resolves with `issuer` set to the `freepod` realm
- [x] 3.2 Confirm the realm's group membership mapper has `full.path = false`,
      so the `groups` claim carries bare names
- [x] 3.3 Send a test email from the realm (via a throwaway registration or the
      admin console test button) to prove SMTP works — the migrated users'
      password reset depends on it
- [x] 3.4 Delete any throwaway account created during SMTP verification

## 4. Phase 3 — Seed the migrated accounts

Tasks 4.2 through 4.6 are the **optional** password-hash carry-over. Skip them
and the migration still completes correctly — accounts are seeded
credential-less and users reset. Exercising them spares users a reset and
removes new-realm SMTP as a shared point of failure for all access. They belong
here and nowhere later: once cutover has happened and users have begun
resetting, writing an exported credential would silently revert a password they
have already changed.

- [x] 4.1 Write a seeding script (`var/` or `scripts/`) that creates users via
      the Keycloak admin REST API with `emailVerified: true`, `enabled: true`,
      **no** `requiredActions`, and **no** role mappings, taking an optional
      `credentials` array per user
- [x] 4.2 OPTIONAL: decide whether to carry password hashes, and for which
      accounts — carrying them for internal accounts only, and letting external
      users reset, is a legitimate choice.
      **Decided (Erik)**: carry hashes, with `fred` as the single gate account.
      The remaining four are seeded only after `fred` is confirmed to sign in
      with his pre-migration password
- [x] 4.3 OPTIONAL: export credentials inside the Keycloak pod with
      `kc.sh export --realm master --users same_file --dir /tmp/kcexport` and
      copy the resulting JSON out
- [x] 4.4 OPTIONAL: from each exported user keep `username`, `email`,
      `emailVerified`, `enabled`, `firstName`, `lastName`, `createdTimestamp`
      and `credentials`; strip `id`, `realmRoles`, `clientRoles` and `groups`
- [x] 4.5 OPTIONAL **gate**: seed exactly one chosen account with its
      `secretData` / `credentialData` via `POST /admin/realms/freepod/users` and
      confirm it signs in with its pre-migration password. The admin API redacts
      `secretData` on read, so this is the only way to prove the write path
      round-trips.
      **Gate PASSED**: `fred` seeded with his carried credential and confirmed
      by Erik to sign in with his pre-migration password. Carry-over is
      therefore proven for the remaining accounts
- [x] 4.6 OPTIONAL: if the gate fails, abandon carry-over and seed every account
      credential-less — nothing is lost; if it passes, seed each remaining
      chosen account with its credential and verify each signs in
- [x] 4.7 Seed all remaining end-user accounts (`erik`, `erik2`, `fred`, `koen`,
      `timberkelaar`); do **not** seed `admin`, which stays in `master`.
      Satisfied via 4.6 rather than credential-less: the gate passed, so all
      five were seeded **with** their carried password hashes. No account needs
      a reset. `admin` was excluded — it is the Keycloak instance administrator
      and the credential the Terraform provider authenticates with
- [x] 4.8 Verify the self-service password reset flow end to end for one
      credential-less account: request reset, receive email, set password, sign
      in.
      **Verified up to delivery; final leg outstanding.** Because carry-over
      succeeded, no real account is credential-less, so a throwaway
      (`reset-verify`, erik.van.zijst+kcreset@gmail.com, zero credentials) was
      created to exercise the genuine path. Driven through the browser: the
      login page offers "Forgot Password?", the flow accepted a credential-less
      account, returned "You should receive an email shortly", and the relay
      logged `result="Ok" stat="250 2.6.0 Message received"` from purelymail.
      Untested: clicking the action-token link, setting a password and signing
      in — that needs inbox access. The `reset-verify` account is deliberately
      left in place so Erik can finish it; **delete it afterwards**, as in 3.4
- [x] 4.9 Add the appropriate account to the `freepod-dev` group
- [x] 4.10 Add the appropriate account to the `freepod-observability` group
- [x] 4.11 Confirm no role mapping was carried over — in particular that no
      account holds the `master` realm `admin` role
- [x] 4.12 If credentials were exported, securely delete the material from
      `/tmp/kcexport` in the pod and from any local copy

## 5. Phase 4 — Terraform variable reshaping in tf/app

- [x] 5.1 Replace the scalar `oauth2_proxy_client_secret` variable in
      `tf/app/variables.tf` with a `map(string)` keyed by workspace, and add a
      matching client ID map variable
- [x] 5.2 Update `tf/app/secrets.auto.tfvars` to supply both maps with `default`
      and `prod` keys (note: the dev workspace is named `default`, not `dev`)
- [x] 5.3 Add an `allowed_groups` variable to the `tf/app/login` module
- [x] 5.4 Update `tf/app/main.tf` to pass the workspace-indexed client ID and
      secret, and `local.is_prod_workspace ? [] : ["freepod-dev"]` for
      `allowed_groups`
- [x] 5.5 Update `tf/app/login/main.tf`: `oidc-issuer-url` and
      `backend-logout-url` to the `freepod` realm, `clientID`/`clientSecret`
      from the new variables, and `allowed_groups` in the config file

## 6. Phase 5 — Cut over dev and verify

- [x] 6.1 Run `terraform apply` in the `default` workspace of `tf/app`.
      **Required an unplanned fix**: tasks 2.5/2.6 set
      `pkce_code_challenge_method = "S256"` on the Keycloak clients, which makes
      PKCE *mandatory*, but nothing in phase 4 enabled it on the oauth2-proxy
      side. oauth2-proxy only sends a code challenge when
      `--code-challenge-method` is set; it logged a warning, started normally
      and went Ready, while every authorization request was rejected with
      `error=invalid_request, Missing parameter: code_challenge_method`.
      Confirmed against the live authorization endpoint before any user tested
      it: without a challenge -> 302 carrying that error, with an S256
      challenge -> 200. `code-challenge-method = "S256"` added to
      `tf/app/login/main.tf` extraArgs and re-applied. The flag and the client
      attribute are a matched pair
- [x] 6.2 Confirm the oauth2-proxy pod reaches Ready (a failed OIDC discovery
      keeps it from starting). Ready with 0 restarts; log shows
      "Performing OIDC Discovery..." then "OAuthProxy configured for Keycloak
      OIDC Client ID: freepod-dev", and `allowed_groups = ["freepod-dev"]` is
      present in the deployed ConfigMap.
      **NOTE**: pod-Ready is necessary but NOT sufficient — see 6.1's PKCE
      finding. oauth2-proxy started happily with a configuration under which
      every login failed
- [x] 6.3 Verify a `freepod-dev` group member can sign in to
      `dev.freepod.eu` and reach an authenticated route.
      Verified with a temporary account (`dev-gate-test`): once added to
      `freepod-dev` it reached `/api/me` and got its identity back. The
      transition from denied to allowed took effect on the very next request
      with no re-authentication, confirming the per-request enforcement in
      design Decision 5. Temporary account and the app-side user row it created
      have both been deleted. Erik additionally confirmed that `erik` signs in
      to dev.freepod.eu — which also validates his carried password hash — and
      that `fred`, who is not a `freepod-dev` member, is denied
- [x] 6.4 Verify a non-member is denied on `dev.freepod.eu` and that the
      session cookie is cleared
- [x] 6.5 Verify anonymous reads still succeed on `dev.freepod.eu` for
      `skip_auth_routes` paths (product catalog, plans, `/api/openapi.json`)
- [x] 6.6 Verify sign-out at `dev.freepod.eu/oauth2/sign_out` terminates the
      Keycloak SSO session against the `freepod` realm

## 7. Phase 6 — Cut over prod

- [x] 7.1 Run `terraform apply` in the `prod` workspace of `tf/app`
- [x] 7.2 Confirm no `allowed_groups` restriction is present in the prod
      oauth2-proxy configuration
- [x] 7.3 Verify sign-in, sign-out, and anonymous landing-page load on
      `freepod.eu`
- [x] 7.4 Verify a newly self-registered account can sign in to `freepod.eu` and
      is **not** able to access `dev.freepod.eu`. Registered `prod-reg-test`
      through the real registration form on freepod.eu. Keycloak created it
      `emailVerified=false` with `requiredActions: ["VERIFY_EMAIL"]` and
      blocked login at `execution=VERIFY_EMAIL` — confirming the realm enforces
      verification on the self-registration path. Verification email delivered
      (`result="Ok"` at the relay). The link click itself was **substituted**
      with an admin-API completion of the verification step (the action-token
      link leg remains covered by the pending 4.8 `reset-verify` test). The
      account then signed in to freepod.eu and reached `/api/me`, and the same
      session was refused `403` on dev.freepod.eu — shared authentication,
      per-environment authorization. Keycloak account and the prod app-side row
      it created have both been deleted

## 8. Phase 7 — Grafana and UI

- [x] 8.1 Update the three OIDC URLs in `tf/deps/prometheus/grafana.tf`
      (`auth_url`, `token_url`, `api_url`) to the `freepod` realm
- [x] 8.2 Point Grafana at the Terraform-managed `grafana` client secret.
      Both the client ID and secret now come from
      `module.keycloak_config.grafana_client_{id,secret}` rather than tfvars,
      and the `grafana_oidc_client_id` / `grafana_oidc_client_secret` root
      variables plus the `secrets.auto.tfvars` entry were removed — this was
      the last hand-maintained Keycloak secret in `tf/deps`
- [x] 8.3 Apply `tf/deps` and verify a `freepod-observability` member can sign
      in to `grafana.freepod.eu`, and that a non-member is refused. Applied
      (2 resources changed, nothing else touched). Verified with a temporary
      account: as a non-member, refused with "IdP did not return a role
      attribute" (`role_attribute_strict` denying the empty JMESPath result);
      after adding it to `freepod-observability`, signed in successfully via
      Generic OAuth and resolved by email. Temporary account removed from both
      Keycloak and Grafana. Also confirmed live that Grafana's authorization
      request carries **no** `code_challenge`, which is why the `grafana`
      client must not require PKCE
- [x] 8.4 Update `VITE_KEYCLOAK_ACCOUNT_URL` in `ui/.env.production` to the
      `freepod` realm account console, keeping it set and non-empty (it doubles
      as the proxy-auth feature flag)
- [x] 8.5 Rebuild and republish the UI image via `scripts/build-images.sh` —
      Vite inlines this value at build time, so no Terraform apply can change it
- [x] 8.6 Roll out the new UI image to both environments and verify the account
      link opens the `freepod` realm account console.
      **Dev done, prod blocked on a merge.** Dev tracks `:latest` and now runs
      digest `sha256:27cfef3c…`; the bundle served by dev.freepod.eu contains
      `realms/freepod/account` and no `realms/master/account`. Prod tracks
      `:master`, which is only produced by a build on the master branch, so
      freepod.eu still serves the stale bundle pointing at the `master` realm
      account console. Not outage-causing (the link resolves, it just shows an
      account page for an identity that no longer lives there), but wrong.
      Resolve by merging this branch and rebuilding, or by pinning
      `var.ui_image` to an immutable tag — a decision about running unmerged
      code in prod, so left to Erik. **Resolved**: PR #63 merged and rolled
      out; freepod.eu now serves a bundle containing `realms/freepod/account`
      and no `realms/master/account`

## 9. Phase 8 — Cleanup after soak

- [x] 9.1 Confirm the soak period has elapsed with no authentication issues
      reported.
      **Soak WAIVED, not elapsed.** Cutover and cleanup both happened on
      2026-08-10, hours apart. The risk was raised explicitly — Phase 8
      dismantles the cheap rollback path — and Erik chose to proceed anyway.
      Recorded here rather than ticked silently, because a future reader
      comparing the plan to what happened deserves to see that this gate was a
      decision and not an observation. Mitigation: a fresh `pg_dump` and
      `partial-export` were captured immediately before the destructive step
      (`var/keycloak-db-2026-08-10-pre-cleanup.sql.gz`,
      `var/keycloak-master-partial-export-2026-08-10-pre-cleanup.json`), so
      rollback is still possible — it just now requires a database restore
      rather than a code revert
- [x] 9.2 Set `registrationAllowed = false` on the `master` realm
- [x] 9.3 Delete the `caelus-dev` client from the `master` realm
- [x] 9.4 Delete the five migrated end-user accounts from the `master` realm,
      retaining `admin`. `erik`, `erik2`, `fred`, `koen` and `timberkelaar`
      deleted; `master` now holds only `admin`. Verified afterwards that the
      9.2 full-representation PUT changed `registrationAllowed` and nothing
      else — themes, SMTP, session timeouts and every other attribute match
      the pre-cleanup export
- [x] 9.5 Remove the now-unused `oauth2_proxy_client_secret` scalar variable if
      any references remain. Done as part of 5.1/5.2 — the scalar was replaced
      rather than left alongside the maps, in `tf/app/variables.tf` and in
      `secrets.auto.tfvars`. Leaving it would have produced an "undeclared
      variable" warning on every plan. No references remain (verified by grep)

## 10. Documentation

- [x] 10.1 Update `api/README.md` where it describes the production auth chain,
      noting the `freepod` realm and the dev group gate
- [x] 10.2 Update `tf/deps/README.md` and `tf/app/README.md` for the new
      Keycloak configuration module and the workspace-keyed secret maps
- [x] 10.3 Record in `tf/README.md` that Keycloak realm config is Terraform-owned
      and that admin-console edits are reverted on apply
- [x] 10.4 Add a `var/` runbook covering the cutover and the rollback procedure
      (revert Terraform, rebuild UI, users sign in with pre-migration
      credentials)
