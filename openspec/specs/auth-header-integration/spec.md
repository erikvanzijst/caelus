# auth-header-integration Specification

## Purpose
Ensure the X-Auth-Request-Email header is properly forwarded from oauth2-proxy to Caelus.

## ADDED Requirements

### Requirement: oauth2-proxy injects X-Auth-Request-Email header
The system SHALL configure oauth2-proxy to set the X-Auth-Request-Email header with authenticated user email.

#### Scenario: X-Auth-Request-Email header is set
- **WHEN** oauth2-proxy configuration includes `SET_XAUTHREQUEST=1`
- **AND** `SET_XAUTHREQUEST` is enabled
- **THEN** the header `X-Auth-Request-Email` is present in requests to upstream

### Requirement: oauth2-proxy preserves existing headers
The system SHALL configure oauth2-proxy to pass through existing X-Auth-Request headers.

#### Scenario: X-Auth-Request headers are preserved
- **WHEN** oauth2-proxy configuration is checked
- **THEN** the option to pass through auth request headers is enabled

### Requirement: Caelus receives X-Auth-Request-Email header
The system SHALL ensure Caelus backend receives the X-Auth-Request-Email header.

#### Scenario: Backend receives email header
- **WHEN** a request is made through oauth2-proxy to Caelus
- **THEN** the `X-Auth-Request-Email` header is present in the request to the upstream service

### Requirement: Email claim maps correctly from Keycloak
The system SHALL ensure the email from Keycloak OIDC claim maps to the X-Auth-Request-Email header.

#### Scenario: Email claim is extracted
- **WHEN** oauth2-proxy is configured
- **THEN** the OIDC claim `email` is mapped to header `X-Auth-Request-Email`

### Requirement: Unauthenticated requests are redirected
The system SHALL redirect unauthenticated users to Keycloak login.

#### Scenario: Unauthenticated request triggers redirect
- **WHEN** a user accesses Caelus without a session
- **THEN** they are redirected to Keycloak authorization endpoint

### Requirement: Authenticated requests pass through
The system SHALL allow authenticated requests to pass through to Caelus.

#### Scenario: Authenticated request passes
- **WHEN** a user with valid OAuth token accesses Caelus
- **THEN** the request reaches Caelus with X-Auth-Request-Email header

### Requirement: Session cookie is handled correctly
The system SHALL configure oauth2-proxy cookie settings for secure operation.

#### Scenario: Cookie settings are secure
- **WHEN** oauth2-proxy configuration is checked
- **THEN** `COOKIE_SECURE` is set appropriately for the environment
- **AND** `COOKIE_DOMAIN` is configured if needed

### Requirement: Caelus Ingress routes through oauth2-proxy
The system SHALL configure the Caelus Ingress to route through oauth2-proxy.

#### Scenario: Caelus Ingress uses oauth2-proxy
- **WHEN** Kubernetes Ingress for Caelus is inspected
- **THEN** the backend service points to oauth2-proxy
