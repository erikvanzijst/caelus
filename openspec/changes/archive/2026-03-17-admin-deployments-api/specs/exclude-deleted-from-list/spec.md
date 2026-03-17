## MODIFIED Requirements

### Requirement: Deployment list excludes deleted deployments
The `list_deployments` service function SHALL exclude deployments with `status == 'deleted'` from its results. This applies to both user-scoped listings (`GET /api/users/{user_id}/deployments`) and the admin listing (`GET /api/deployments`).

#### Scenario: User lists their deployments
- **GIVEN** a user has deployments with statuses `ready`, `provisioning`, and `deleted`
- **WHEN** they request `GET /api/users/{user_id}/deployments`
- **THEN** only deployments with status `ready` and `provisioning` SHALL be returned
- **AND** deployments with status `deleted` SHALL NOT be included

#### Scenario: Deleting status is still visible
- **GIVEN** a deployment with status `deleting` (deletion in progress)
- **WHEN** the user lists their deployments
- **THEN** the `deleting` deployment SHALL be included in the results

### Requirement: Remove client-side deleted deployment filter
The `Dashboard.tsx` component SHALL NOT filter deployments by status client-side. The server-side filter makes this unnecessary.
