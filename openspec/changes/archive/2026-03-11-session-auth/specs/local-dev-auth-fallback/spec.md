## Purpose
Frontend email dialog and header injection for local development when no auth proxy is present, enabling transparent backend behavior across environments.

## ADDED Requirements

### Requirement: Frontend SHALL initialize session via GET /api/me
The system MUST use `GET /api/me` as the sole session initialization mechanism on frontend startup.

#### Scenario: Startup in production (behind oauth2-proxy)
- **WHEN** the frontend loads in production and `GET /api/me` is called
- **AND** oauth2-proxy has injected `X-Auth-Request-Email` at the proxy layer
- **THEN** the API SHALL return `200` with the user object
- **AND** the frontend SHALL store the user in memory and proceed to the Dashboard

#### Scenario: Startup in local dev (no auth proxy)
- **WHEN** the frontend loads in local dev with no stored auth headers and `GET /api/me` is called
- **AND** no `X-Auth-Request-Email` header is present
- **THEN** the API SHALL return `404`
- **AND** the frontend SHALL display the email dialog

#### Scenario: Startup in local dev with previously stored email
- **WHEN** the frontend loads in local dev and localStorage contains auth headers with a valid email
- **THEN** `GET /api/me` SHALL be called with the stored `X-Auth-Request-Email` header
- **AND** the API SHALL return `200` with the user object
- **AND** the frontend SHALL proceed to the Dashboard without showing the email dialog

### Requirement: Email dialog SHALL populate localStorage auth headers
The system MUST store the user-provided email as a request header in localStorage for use in all subsequent API calls.

#### Scenario: User submits email in dialog
- **WHEN** a user enters an email address in the email dialog and submits
- **THEN** the frontend SHALL store `{"X-Auth-Request-Email": "<email>"}` in localStorage auth headers
- **AND** the frontend SHALL retry `GET /api/me` with the new header
- **AND** on `200` the frontend SHALL store the user in memory and proceed to the Dashboard

### Requirement: Auth headers in localStorage SHALL be applied unconditionally to all API requests
The system MUST spread localStorage auth headers into every outgoing API request, regardless of environment.

#### Scenario: Production with empty headers
- **WHEN** the frontend makes an API request in production
- **AND** localStorage auth headers is empty (`{}`)
- **THEN** no extra headers are added to the request (oauth2-proxy handles authentication at the proxy layer)

#### Scenario: Local dev with stored headers
- **WHEN** the frontend makes an API request in local dev
- **AND** localStorage auth headers contains `{"X-Auth-Request-Email": "user@example.com"}`
- **THEN** the request SHALL include the `X-Auth-Request-Email: user@example.com` header

### Requirement: Switch user button SHALL be removed
The frontend MUST NOT display a "Switch user" button or similar UI element for changing identity.

#### Scenario: AppShell user display
- **WHEN** the AppShell renders with an authenticated user
- **THEN** the user's email SHALL be displayed
- **AND** no button or link to switch or change user identity SHALL be present

### Requirement: Client-side user creation logic SHALL be removed from Dashboard
The Dashboard MUST NOT contain user lookup-by-email or auto-creation logic; this is now a backend responsibility.

#### Scenario: Dashboard loads with authenticated user
- **WHEN** the Dashboard page renders
- **THEN** it SHALL use the user object already resolved during session initialization
- **AND** it SHALL NOT call `GET /api/users` to find the current user
- **AND** it SHALL NOT call `POST /api/users` to create the current user
