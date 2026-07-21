## ADDED Requirements

### Requirement: Deployments persist the accepted ToS version

A deployment MUST persist the Terms of Service version supplied at creation in a
NOT NULL column. The stored value MUST be the version the client supplied,
recorded verbatim (the API does not substitute a server-side "current" version).

#### Scenario: New deployment stores the supplied version

- **WHEN** a deployment is created with `tos_version` `2026-07-01`
- **THEN** the persisted deployment records `tos_version` `2026-07-01`

#### Scenario: Existing deployments are backfilled

- **WHEN** the migration adding the column is applied to a database with
  existing deployments
- **THEN** those deployments have `tos_version` `2026-07-01` (the current ToS
  effective date) and the column is NOT NULL

### Requirement: Deployment reads return the accepted ToS version

Deployment read responses (REST and CLI) MUST include the persisted
`tos_version` so clients can compare a deployment's accepted version against the
current terms.

#### Scenario: Read returns the recorded version

- **WHEN** a client retrieves a deployment created with `tos_version`
  `2026-07-01`
- **THEN** the read response includes `tos_version` `2026-07-01`

#### Scenario: Read of a backfilled pre-existing deployment

- **WHEN** a client retrieves a deployment created before this capability
- **THEN** the read response includes `tos_version` `2026-07-01` (the backfilled
  value)

### Requirement: CLI parity for supplying the ToS version

The Typer create-deployment command MUST accept a `--tos-version` option that is
functionally equivalent to the REST field: it is required to create a
deployment and is persisted and returned identically.

#### Scenario: CLI create records the version

- **WHEN** an operator runs the create-deployment CLI command with
  `--tos-version 2026-07-01`
- **THEN** the created deployment records and returns `tos_version` `2026-07-01`

#### Scenario: CLI create without the option is rejected

- **WHEN** an operator runs the create-deployment CLI command without
  `--tos-version`
- **THEN** the command fails without creating a deployment
