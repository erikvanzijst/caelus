## RENAMED Requirements

### Requirement: Absence semantics for deployments without file access
- **FROM:** Absence semantics for deployments without file access
- **TO:** Absence semantics for deployments without SSH access

## MODIFIED Requirements

### Requirement: Absence semantics for deployments without SSH access
The endpoint MUST distinguish "this deployment has no SSH access" from transient errors, returning a stable not-found response the UI can use to hide the feature.

Availability MUST be determined by what a deployment's chart actually renders, and the platform MUST NOT decide it by a marker that only one access profile emits. Both profiles grant SSH access and both are addressed through the same endpoint; a check written against the older profile's marker reports "no access" for every deployment on the newer one, which is a false negative in the one direction nobody notices — the feature simply disappears from the interface, while SSH itself keeps working because the edge resolves connections from the platform's records rather than from cluster labels.

#### Scenario: Product with no SSH access
- **WHEN** the owner requests details for a deployment whose chart renders no SSH resources
- **THEN** the API responds with 404 and a stable error body indicating SSH access is not available for this deployment

#### Scenario: Deployment on either profile reports available
- **WHEN** the owner requests details for a deployment on the `sftp` profile, and for one on the `dev` profile
- **THEN** both report the deployment's access details rather than a not-found

#### Scenario: Availability tracks what the chart renders
- **WHEN** the chart changes which marker it applies to a deployment's SSH resources
- **THEN** the platform's availability check follows it, rather than silently reporting no access
