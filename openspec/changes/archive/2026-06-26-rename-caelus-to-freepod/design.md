## Context

The product has been known internally and externally as "Caelus" since inception. The name appears in two categories of places: user-facing surfaces (UI text, browser title, error messages, domain names, email sender) and internal identifiers (Python class names, localStorage keys, DB schema, env vars, K8s namespace names, Helm values namespaces, container image names).

The internal identifiers are frozen — renaming them would require coordinated changes across schema migrations, CI pipelines, deployment tooling, and documentation with no user-visible benefit and meaningful risk. Only the user-facing surfaces are in scope.

The production stack: a load balancer terminates TLS and reverse-proxies to a k3s cluster. Keycloak provides OIDC authentication via oauth2-proxy. The app domain is currently `app.deprutser.be`; the new domain is `freepod.eu`.

Prerequisites already complete: DNS for `freepod.eu` / `dev.freepod.eu` resolves to the LB; `*.freepod.eu` and `*.dev.freepod.eu` TLS certs are active at the LB layer; `noreply@freepod.eu` email exists.

## Goals / Non-Goals

**Goals:**
- Every string a user reads says "Freepod", not "Caelus"
- The app is reachable at `freepod.eu` (prod) and `dev.freepod.eu` (dev)
- Keycloak is reachable at `keycloak.freepod.eu`
- Outbound email is sent from `noreply@freepod.eu`

**Non-Goals:**
- Renaming internal code identifiers (class names, env vars, DB columns, K8s namespaces)
- Renaming the GitHub repo or container images
- Keeping the old `app.deprutser.be` domain alive as a redirect
- Zero-downtime cutover (brief auth outage is acceptable)

## Decisions

### 1. Freeze the internal/external naming boundary

The `caelus.svg` icon filename, localStorage keys (`caelus.auth.*`), Python class names, and Helm values namespace (`caelus.plan.*`) are treated as internal implementation details and left unchanged. This is the key risk-reduction decision: it confines the diff to string literals in UI components, one API file, and Terraform domain values.

_Alternative considered_: rename everything end-to-end. Rejected because it requires a DB migration, env var changes across all deployment tooling, and CI pipeline updates — none of which are visible to users.

### 2. Ordered two-phase Terraform apply

The Keycloak OIDC issuer URL is embedded in JWT `iss` claims and in Keycloak's own discovery metadata. `tf/deps` (which configures Keycloak's `KC_HOSTNAME_URL`) must be applied and Keycloak must restart _before_ `tf/app` is applied (which updates oauth2-proxy's `oidc-issuer-url`). Applying both simultaneously would leave oauth2-proxy pointing at a Keycloak that still advertises the old issuer, breaking OIDC token validation.

_Rollback_: Revert `tf/deps/main.tf` and re-apply `tf/deps`, then revert and re-apply `tf/app`. DNS changes are external and not rolled back automatically.

### 3. Hard cutover, no redirect

`app.deprutser.be` will simply stop being routed once Terraform is applied. No 301 redirect is configured. This is acceptable given the acknowledged downtime window and removes the operational burden of maintaining parallel ingress rules.

## Risks / Trade-offs

- **Auth outage window** → Between `tf/deps apply` (Keycloak restarts with new hostname) and `tf/app apply` (oauth2-proxy updates), authentication will fail. Mitigation: apply both Terraform modules back-to-back; the window is only as long as a Keycloak startup (~30s).

- **SMTP deliverability** → Changing `smtp_username` from `caelus@deprutser.be` to `noreply@freepod.eu` requires that SPF/DKIM records for `freepod.eu` authorize the configured SMTP relay. Mitigation: verify DNS email records before cutover.

- **User deployments under wildcard** → Users may have pods provisioned under `*.app.deprutser.be`. After cutover, those hostnames will stop resolving (the old domain is retired). Users will need to update their deployment hostnames to `*.freepod.eu`. Mitigation: wildcard `*.freepod.eu` is already in DNS/TLS; users can re-provision.

## Migration Plan

1. Merge code changes (UI + API copy, Terraform files)
2. Verify `freepod.eu`, `dev.freepod.eu`, `keycloak.freepod.eu` DNS resolves
3. Verify SPF/DKIM for `freepod.eu` email
4. `cd tf/deps && terraform apply` → Keycloak restarts with `KC_HOSTNAME_URL=keycloak.freepod.eu`
5. Wait for Keycloak pod to be `Running` (typically ~30s)
6. `cd tf/app && terraform apply` → App switches to `freepod.eu`, oauth2-proxy points to new Keycloak URL
7. Smoke test: load `https://freepod.eu`, authenticate, verify email
