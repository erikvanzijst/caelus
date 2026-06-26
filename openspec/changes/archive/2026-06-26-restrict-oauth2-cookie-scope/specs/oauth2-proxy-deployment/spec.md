## MODIFIED Requirements

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
