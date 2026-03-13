## ADDED Requirements

### Requirement: Hostname check endpoint returns usability status
The system MUST provide a `GET /api/hostnames/{fqdn}` endpoint that validates whether the given FQDN can be used for a Caelus deployment and returns a JSON response with the FQDN and a reason for failure (or null on success).

#### Scenario: Usable hostname
- **WHEN** a client sends `GET /api/hostnames/myapp.app.deprutser.be` and the hostname passes all validation checks
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "myapp.app.deprutser.be", "reason": null}`

#### Scenario: Invalid hostname format
- **WHEN** a client sends `GET /api/hostnames/-bad..host` and the hostname fails format validation
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "-bad..host", "reason": "invalid"}`

#### Scenario: Reserved hostname
- **WHEN** a client sends `GET /api/hostnames/smtp.app.deprutser.be` and the hostname is in the reserved list
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "smtp.app.deprutser.be", "reason": "reserved"}`

#### Scenario: Hostname already in use
- **WHEN** a client sends `GET /api/hostnames/taken.app.deprutser.be` and an active deployment uses that hostname
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "taken.app.deprutser.be", "reason": "in_use"}`

#### Scenario: Hostname does not resolve to Caelus
- **WHEN** a client sends `GET /api/hostnames/example.com` and DNS does not resolve to the configured LB IPs
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "example.com", "reason": "not_resolving"}`

### Requirement: Hostname check endpoint requires authentication
The `GET /api/hostnames/{fqdn}` endpoint MUST require the `X-Auth-Request-Email` header for authentication, consistent with other API endpoints.

#### Scenario: Unauthenticated request
- **WHEN** a client sends `GET /api/hostnames/test.example.com` without the `X-Auth-Request-Email` header
- **THEN** the endpoint returns HTTP 401 or 403

### Requirement: Hostname check endpoint is synchronous
The `GET /api/hostnames/{fqdn}` endpoint MUST be implemented as a synchronous endpoint (`def`, not `async def`) so that FastAPI dispatches it to a threadpool and database access does not block the event loop.

#### Scenario: Endpoint handles concurrent requests
- **WHEN** multiple clients call the hostname check endpoint simultaneously
- **THEN** each request runs in its own thread and does not block others

### Requirement: Hostname check response model has exactly two fields
The response model MUST contain exactly two fields: `fqdn` (string) and `reason` (string or null). No additional fields such as `valid`, `available`, `resolving`, or `usable` SHALL be included.

#### Scenario: Response shape
- **WHEN** the endpoint returns a response
- **THEN** the JSON body contains only the keys `fqdn` and `reason`
