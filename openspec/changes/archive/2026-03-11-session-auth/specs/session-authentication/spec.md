## Purpose
Backend authentication via X-Auth-Request-Email header with auto-creation of unknown users and injection of authenticated user context into all API endpoints and CLI commands.

## ADDED Requirements

### Requirement: GET /api/me SHALL return the authenticated user or 404
The system MUST provide a `GET /api/me` endpoint that resolves the authenticated user from the request header.

#### Scenario: Authenticated user exists
- **WHEN** a request to `GET /api/me` includes a valid `X-Auth-Request-Email` header with an email matching an existing user
- **THEN** the API SHALL return `200` with a `UserRead` response body containing the user's `id`, `email`, `is_admin`, and `created_at`

#### Scenario: Authenticated user does not exist yet
- **WHEN** a request to `GET /api/me` includes a valid `X-Auth-Request-Email` header with an email not matching any existing user
- **THEN** the API SHALL auto-create a new user record for that email and return `200` with the newly created `UserRead`

#### Scenario: Email matching is case-insensitive
- **WHEN** a request to `GET /api/me` includes `X-Auth-Request-Email: Alice@Example.COM`
- **AND** a user with email `alice@example.com` exists
- **THEN** the API SHALL return the existing user, not create a duplicate

#### Scenario: No auth header present
- **WHEN** a request to `GET /api/me` does not include an `X-Auth-Request-Email` header
- **THEN** the API SHALL return `404`

### Requirement: All API endpoints SHALL have authenticated user context injected
The system MUST inject the resolved authenticated user into every API endpoint function via FastAPI dependency injection.

#### Scenario: Endpoint receives current user
- **WHEN** a request with a valid `X-Auth-Request-Email` header reaches any API endpoint
- **THEN** the endpoint function SHALL have access to the authenticated `UserORM` via the `get_current_user` dependency

#### Scenario: Endpoint without auth header
- **WHEN** a request without `X-Auth-Request-Email` header reaches any API endpoint (other than `/api/me`)
- **THEN** the endpoint SHALL return `404`

### Requirement: Auto-created users SHALL use the same data model as manually created users
The system MUST create auto-provisioned user records that are indistinguishable from users created through `POST /api/users`.

#### Scenario: Auto-created user record
- **WHEN** a user is auto-created via `GET /api/me` or any authenticated endpoint
- **THEN** the user record SHALL have a valid integer `id`, the provided email (normalized), `is_admin` set to `false`, and `created_at` set to the current time
- **AND** the user SHALL be retrievable via `GET /api/users/{id}` and appear in `GET /api/users` listings

### Requirement: CLI SHALL authenticate via environment variable with optional override
The system MUST support CLI authentication through the `CAELUS_USER_EMAIL` environment variable.

#### Scenario: CLI reads CAELUS_USER_EMAIL
- **WHEN** a CLI command is executed with `CAELUS_USER_EMAIL` set
- **THEN** the CLI SHALL resolve the email to a user via the same lookup/auto-create logic as the API

#### Scenario: --as-user overrides environment variable
- **WHEN** a CLI command is executed with both `CAELUS_USER_EMAIL` set and `--as-user another@example.com` provided
- **THEN** the CLI SHALL use `another@example.com` as the authenticated email, ignoring the environment variable

#### Scenario: No email configured
- **WHEN** a CLI command requiring user context is executed without `CAELUS_USER_EMAIL` set and without `--as-user`
- **THEN** the CLI SHALL exit with a clear error message indicating that authentication is required

### Requirement: Backend SHALL treat auth header identically regardless of source
The system MUST not distinguish between headers set by oauth2-proxy and headers set by the frontend client.

#### Scenario: Production header from oauth2-proxy
- **WHEN** oauth2-proxy sets `X-Auth-Request-Email` on a proxied request
- **THEN** the backend SHALL resolve the user using the same logic as any other source

#### Scenario: Local-dev header from frontend
- **WHEN** the frontend JavaScript sets `X-Auth-Request-Email` directly on a fetch request
- **THEN** the backend SHALL resolve the user using the same logic as any other source
