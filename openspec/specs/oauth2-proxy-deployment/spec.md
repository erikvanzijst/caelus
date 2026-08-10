# oauth2-proxy-deployment Specification

## Purpose
Deploy oauth2-proxy as an authentication gateway in front of Caelus.
## Requirements
### Requirement: oauth2-proxy runs on Kubernetes
The system SHALL deploy oauth2-proxy as a Kubernetes Deployment.

#### Scenario: oauth2-proxy deployment exists
- **WHEN** `kubectl get deployment -n auth-system oauth2-proxy` is executed
- **THEN** a deployment named `oauth2-proxy` exists in the `auth-system` namespace

#### Scenario: oauth2-proxy pod is running
- **WHEN** `kubectl get pods -n auth-system -l app=oauth2-proxy` is executed
- **THEN** at least one pod shows status `Running`

### Requirement: oauth2-proxy authenticates against Keycloak
The system SHALL configure oauth2-proxy to use the Keycloak `freepod` realm as
its OIDC provider, with the client ID and client secret selected per Terraform
workspace so that each environment authenticates against its own Keycloak
client.

#### Scenario: oauth2-proxy is configured with Keycloak OIDC
- **WHEN** oauth2-proxy deployment configuration is inspected
- **THEN** `oidc-issuer-url` is
  `https://keycloak.freepod.eu/realms/freepod`
- **AND** the client ID is configured
- **AND** the client secret references a Kubernetes Secret

#### Scenario: Each environment uses its own client
- **WHEN** oauth2-proxy is deployed from the `prod` workspace
- **THEN** it is configured with the `freepod-prod` client ID and secret
- **WHEN** oauth2-proxy is deployed from the `default` workspace
- **THEN** it is configured with the `freepod-dev` client ID and secret

#### Scenario: Issuer is reachable before rollout
- **WHEN** oauth2-proxy starts
- **THEN** the configured issuer's OIDC discovery document resolves
- **AND** a discovery failure prevents the pod from becoming ready, so the realm
  and clients MUST exist before this configuration is applied

### Requirement: oauth2-proxy forwards X-Auth-Request-Email header
The system SHALL configure oauth2-proxy to inject the user email as `X-Auth-Request-Email` header.

#### Scenario: Email header is set in oauth2-proxy config
- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `SET_XAUTHREQUEST` is enabled
- **AND** `EMAIL_DOMAIN` is configured appropriately

### Requirement: oauth2-proxy routes to Caelus backend
The system SHALL configure oauth2-proxy to proxy authenticated requests to Caelus.

#### Scenario: Upstream is configured
- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `UPSTREAM` points to the Caelus service URL

### Requirement: oauth2-proxy is accessible via Ingress
The system SHALL expose the browser-facing oauth2-proxy `/oauth2/*` endpoints (`start`, `callback`, `sign_out`) on the Caelus apex host `${var.domain}`, routed directly to the oauth2-proxy service **without** the `forward-auth` middleware, so the callback issues the session cookie from the apex host.

#### Scenario: oauth2 endpoints are served on the apex host
- **WHEN** a request is made to `https://${var.domain}/oauth2/start`, `/oauth2/callback`, or `/oauth2/sign_out`
- **THEN** the request is routed to the oauth2-proxy service
- **AND** the route does not apply the `forward-auth` middleware (the endpoints are reachable unauthenticated)

#### Scenario: Redirect URL targets the apex callback
- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `redirect-url` is `https://${var.domain}/oauth2/callback`
- **AND** `whitelist_domains` includes `${var.domain}`

### Requirement: oauth2-proxy has health checks
The system SHALL configure readiness and liveness probes for oauth2-proxy.

#### Scenario: oauth2-proxy probes are configured
- **WHEN** oauth2-proxy deployment spec is inspected
- **THEN** both readinessProbe and livenessProbe are defined

### Requirement: oauth2-proxy session is configured
The system SHALL configure oauth2-proxy session handling so the session cookie is scoped **host-only** to the Caelus apex domain (`var.domain`) and is never sent to wildcard user-app subdomains.

#### Scenario: Session configuration is set
- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `COOKIE_SECRET` references a Kubernetes Secret
- **AND** session type is configured (cookie-based or Redis if high availability)

#### Scenario: Cookie is host-only to the apex domain
- **WHEN** a user completes login and the `Set-Cookie` for `_oauth2_proxy` is inspected
- **THEN** the cookie has **no** `Domain` attribute (host-only), bound to `${var.domain}`
- **AND** `cookie_domains` is not set in the oauth2-proxy configuration

#### Scenario: Cookie is not sent to user-app subdomains
- **WHEN** the browser issues a request to a deployed user app at `<app>.${var.domain}`
- **THEN** no `_oauth2_proxy*` cookie is included in the request

### Requirement: oauth2-proxy resources are managed by Terraform
The system SHALL provision oauth2-proxy Kubernetes resources via Terraform.

#### Scenario: Terraform applies oauth2-proxy resources
- **WHEN** `terraform plan` is run in `./tf/`
- **THEN** resources for oauth2-proxy deployment, service, and ingress are planned

### Requirement: The development environment is gated by group membership
The system SHALL restrict access to `dev.freepod.eu` to members of the
`freepod-dev` Keycloak group by configuring oauth2-proxy `allowed_groups` in the
non-prod workspace only. The production environment SHALL remain ungated,
because Freepod is a public service.

#### Scenario: Dev is gated
- **WHEN** oauth2-proxy configuration in the `default` workspace is inspected
- **THEN** `allowed_groups` contains `freepod-dev`

#### Scenario: Prod is not gated
- **WHEN** oauth2-proxy configuration in the `prod` workspace is inspected
- **THEN** no `allowed_groups` restriction is configured

#### Scenario: Group member reaches the dev application
- **WHEN** a member of `freepod-dev` authenticates and requests a protected
  route on `dev.freepod.eu`
- **THEN** the forward-auth check returns 202 with `X-Auth-Request-Email` set
- **AND** the request reaches the upstream application

#### Scenario: Non-member is denied on the dev environment
- **WHEN** an authenticated user who is not a member of `freepod-dev` requests a
  protected route on `dev.freepod.eu`
- **THEN** the forward-auth check denies the request
- **AND** the oauth2-proxy session cookie is cleared

#### Scenario: Group names are unqualified
- **WHEN** `allowed_groups` values are inspected
- **THEN** they are bare group names such as `freepod-dev`
- **AND** they are not slash-prefixed paths, matching the realm's group mapper
  which emits bare names

#### Scenario: Membership changes take effect immediately
- **WHEN** a user is removed from the `freepod-dev` group
- **THEN** their next request is denied, because authorization is evaluated on
  every forward-auth check rather than only at login

### Requirement: Public routes remain reachable on the gated environment
The system SHALL accept that routes listed in `skip_auth_routes` bypass
authorization entirely, so genuinely public reads stay anonymously reachable on
`dev.freepod.eu` even while group gating is active. These routes expose no
tenant data.

#### Scenario: Anonymous catalog read succeeds on dev
- **WHEN** an unauthenticated client requests a route matched by
  `skip_auth_routes` on `dev.freepod.eu`, such as the product catalog
- **THEN** the request succeeds
- **AND** group gating is not applied, because the skip rule short-circuits
  before the authorization check

#### Scenario: Identity is never trusted on skipped routes
- **WHEN** a request to a skipped route carries a client-supplied
  `X-Auth-Request-Email` header
- **THEN** no endpoint matched by a skip rule uses that header for
  authorization, since oauth2-proxy neither injects nor strips it on these
  routes

