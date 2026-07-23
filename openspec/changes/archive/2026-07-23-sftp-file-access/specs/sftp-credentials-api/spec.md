## ADDED Requirements

### Requirement: Deployment-scoped endpoint returns SFTP connection details
The API MUST provide a read endpoint under the deployment resource (`GET /users/{user_id}/deployments/{deployment_id}/sftp`) returning the SFTP host and port for the environment (`freepod.eu:22` in prod, `dev.freepod.eu:23` in dev), plus the username and password for that deployment. Host and port MUST come from per-environment configuration (pydantic-settings) and MUST be the user-facing router values, not the internal HAProxy/cluster ports (2222/2223). The credential values MUST be read from the credentials Secret in the deployment's namespace at request time; SFTP credentials MUST NOT be persisted in the Caelus database.

#### Scenario: Owner retrieves credentials
- **WHEN** the owning user requests the SFTP details of a ready deployment whose product exposes files
- **THEN** the response contains the environment's configured host and port, and the username and password matching the deployment's credentials Secret

#### Scenario: Credentials reflect the cluster state
- **WHEN** the credentials Secret is regenerated (deleted and re-created by reconcile)
- **THEN** a subsequent request returns the new password without any database migration or sync step

### Requirement: Absence semantics for deployments without file access
The endpoint MUST distinguish "this deployment has no SFTP access" (product exposes no PVCs) from transient errors. When no credentials Secret exists for a ready deployment, the API MUST return a stable not-found response the UI can use to hide the feature.

#### Scenario: Product without exposable PVCs
- **WHEN** the owner requests SFTP details for a deployment whose chart renders no SFTP resources
- **THEN** the API responds with 404 and a stable error body indicating SFTP is not available for this deployment

### Requirement: Authorization matches deployment access rules
Access to SFTP details MUST follow the existing deployment authorization model: the owning user and admins MAY read them; other users MUST be denied with the same status codes used by other deployment sub-resources.

#### Scenario: Non-owner is denied
- **WHEN** an authenticated user requests SFTP details of another user's deployment
- **THEN** the request is denied with the platform's standard authorization error

### Requirement: CLI parity
The Typer CLI MUST offer a command functionally identical to the endpoint (same authorization, same data, same absence semantics), consistent with the API/CLI parity convention.

#### Scenario: CLI retrieves credentials
- **WHEN** an operator runs the SFTP details CLI command for a deployment
- **THEN** the output contains the same host, port, username, and password as the REST endpoint
