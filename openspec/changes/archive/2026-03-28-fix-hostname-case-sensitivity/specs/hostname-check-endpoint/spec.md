## MODIFIED Requirements

### Requirement: Hostname check endpoint returns usability status
The system MUST provide a `GET /api/hostnames/{fqdn}` endpoint that validates whether the given FQDN can be used for a Caelus deployment and returns a JSON response with the normalized (lowercased) FQDN and a reason for failure (or null on success).

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

#### Scenario: Hostname does not resolve to Caelus
- **WHEN** a client sends `GET /api/hostnames/example.com` and DNS does not resolve to the configured LB IPs
- **THEN** the endpoint returns HTTP 200 with body `{"fqdn": "example.com", "reason": "not_resolving"}`
