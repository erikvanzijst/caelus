## MODIFIED Requirements

### Requirement: Hostname check endpoint returns usability status
The system MUST provide a `GET /api/hostnames/{fqdn}` endpoint that validates whether the given FQDN can be used for a Caelus deployment and returns a JSON response with the normalized (lowercased) FQDN and a reason for failure (or null on success). The endpoint MUST be accessible without authentication: the response carries no sensitive data and the field validates hostnames as the user types, before any deployment exists.

#### Scenario: Accessible without authentication
- **WHEN** a client sends `GET /api/hostnames/myapp.example.com` without an authentication header
- **THEN** the endpoint returns HTTP 200 with the usability result (it does not require authentication)

#### Scenario: Usable hostname
- **WHEN** a client sends `GET /api/hostnames/myapp.app.deprutser.be` and the hostname passes all validation checks
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "myapp.app.deprutser.be", "reason": null}`

#### Scenario: Mixed-case hostname is normalized in response
- **WHEN** a client sends `GET /api/hostnames/MyApp.App.Deprutser.Be` and the hostname passes all validation checks
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "myapp.app.deprutser.be", "reason": null}`

#### Scenario: Mixed-case hostname detected as in use
- **WHEN** a client sends `GET /api/hostnames/Taken.App.Deprutser.Be` and an active deployment uses hostname `"taken.app.deprutser.be"`
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "taken.app.deprutser.be", "reason": "in_use"}`

#### Scenario: Invalid hostname format
- **WHEN** a client sends `GET /api/hostnames/-bad..host` and the hostname fails format validation
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "-bad..host", "reason": "invalid"}`

#### Scenario: Reserved hostname
- **WHEN** a client sends `GET /api/hostnames/smtp.app.deprutser.be` and the hostname is in the reserved list
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "smtp.app.deprutser.be", "reason": "reserved"}`

#### Scenario: Hostname already in use
- **WHEN** a client sends `GET /api/hostnames/taken.app.deprutser.be` and an active deployment uses that hostname
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "taken.app.deprutser.be", "reason": "in_use"}`

#### Scenario: Custom hostname does not have a CNAME to the platform domain
- **WHEN** a client sends `GET /api/hostnames/example.com` and the FQDN has no CNAME record pointing to `settings.domain` (e.g. it has an A record, no record, or a CNAME to a different target)
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "example.com", "reason": "not_resolving"}`

### Requirement: CNAME target endpoint exposes the platform domain
The system MUST provide a public (unauthenticated) `GET /api/cname-target` endpoint that returns the platform's CNAME target domain (`settings.domain`) as a JSON string, so the UI can render environment-correct CNAME setup instructions. It MUST return an empty string when the domain is unconfigured.

#### Scenario: Returns the configured domain
- **WHEN** a client sends `GET /api/cname-target` and `settings.domain` is `"dev.freepod.eu"`
- **THEN** the endpoint returns HTTP 200 with body `"dev.freepod.eu"`

#### Scenario: Returns empty string when unconfigured
- **WHEN** a client sends `GET /api/cname-target` and `settings.domain` is empty
- **THEN** the endpoint returns HTTP 200 with body `""`
