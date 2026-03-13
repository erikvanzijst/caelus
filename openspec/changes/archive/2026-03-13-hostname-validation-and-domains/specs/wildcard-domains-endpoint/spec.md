## ADDED Requirements

### Requirement: Domains endpoint returns Caelus-provided wildcard domains
The system MUST provide a `GET /api/domains` endpoint that returns the list of Caelus-provided wildcard domain suffixes as a JSON array of strings.

#### Scenario: Wildcard domains configured
- **WHEN** a client sends `GET /api/domains` and `CAELUS_WILDCARD_DOMAINS` is configured with `["app.deprutser.be"]`
- **THEN** the endpoint returns HTTP 200 with body `["app.deprutser.be"]`

#### Scenario: No wildcard domains configured
- **WHEN** a client sends `GET /api/domains` and `CAELUS_WILDCARD_DOMAINS` is not set or empty
- **THEN** the endpoint returns HTTP 200 with body `[]`

#### Scenario: Multiple wildcard domains
- **WHEN** `CAELUS_WILDCARD_DOMAINS` is configured with `["app.deprutser.be", "apps.example.com"]`
- **THEN** the endpoint returns HTTP 200 with body `["app.deprutser.be", "apps.example.com"]`

### Requirement: Domains endpoint does not require explicit authentication
The `GET /api/domains` endpoint MUST NOT enforce authentication via the `X-Auth-Request-Email` header. In production, oauth2-proxy enforces auth at the proxy level regardless.

#### Scenario: Request without auth header
- **WHEN** a client sends `GET /api/domains` without the `X-Auth-Request-Email` header
- **THEN** the endpoint returns HTTP 200 with the domains list (assuming no proxy auth is enforced in the test environment)
