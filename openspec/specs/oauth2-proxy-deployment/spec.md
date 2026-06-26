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
The system SHALL configure oauth2-proxy to use Keycloak as the OIDC provider.

#### Scenario: oauth2-proxy is configured with Keycloak OIDC
- **WHEN** oauth2-proxy deployment environment variables are inspected
- **THEN** `OIDC_ISSUER_URL` points to Keycloak realm URL
- **AND** `OAUTH2_PROXY_CLIENT_ID` is configured
- **AND** `OAUTH2_PROXY_CLIENT_SECRET` references a Kubernetes Secret

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
