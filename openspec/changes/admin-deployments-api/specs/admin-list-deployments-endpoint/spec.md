## ADDED Requirements

### Requirement: Admin endpoint returns all non-deleted deployments
`GET /api/deployments` SHALL return all deployments where `status != 'deleted'`, across all users. The response SHALL be a JSON array of `DeploymentRead` objects. Each object SHALL include the deployment's `user` (with `email`), `desired_template`, and `applied_template` relationships.

#### Scenario: Admin lists all deployments
- **GIVEN** there are deployments owned by multiple users, some with status `deleted`
- **WHEN** an admin sends `GET /api/deployments`
- **THEN** the response status SHALL be `200`
- **AND** the response body SHALL be a JSON array containing all non-deleted deployments
- **AND** deleted deployments SHALL NOT be included

#### Scenario: Non-admin is forbidden
- **GIVEN** a non-admin user
- **WHEN** they send `GET /api/deployments`
- **THEN** the response status SHALL be `403`

#### Scenario: Unauthenticated request
- **GIVEN** no `X-Auth-Request-Email` header
- **WHEN** a request is sent to `GET /api/deployments`
- **THEN** the response status SHALL be `404` (consistent with existing auth behavior)

### Requirement: CLI list-deployments --all flag
The `list-deployments` CLI command SHALL accept an `--all` flag. When `--all` is provided, it SHALL list deployments across all users (not filtered by the current CLI user). The `--all` flag SHALL require the calling user to be an admin.

#### Scenario: Admin lists all deployments via CLI
- **GIVEN** the CLI user is an admin
- **WHEN** they run `list-deployments --all`
- **THEN** all non-deleted deployments across all users SHALL be displayed

#### Scenario: Non-admin uses --all flag
- **GIVEN** the CLI user is not an admin
- **WHEN** they run `list-deployments --all`
- **THEN** the command SHALL fail with a forbidden error
