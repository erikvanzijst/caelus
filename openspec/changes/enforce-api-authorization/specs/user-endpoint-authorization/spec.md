## ADDED Requirements

### Requirement: User listing is admin-only
`GET /api/users` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin lists users
- **WHEN** an admin user sends GET /api/users
- **THEN** the endpoint returns the list of users with HTTP 200

#### Scenario: Non-admin lists users
- **WHEN** a non-admin user sends GET /api/users
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: User creation is admin-only
`POST /api/users` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin creates user
- **WHEN** an admin user sends POST /api/users with a valid payload
- **THEN** the endpoint creates the user and returns HTTP 201

#### Scenario: Non-admin creates user
- **WHEN** a non-admin user sends POST /api/users with a valid payload
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: User deletion is disabled
`DELETE /api/users/{user_id}` SHALL return HTTP 501 Not Implemented with detail "User deletion is not yet implemented" for all users, including admins. The endpoint SHALL NOT perform any deletion logic.

#### Scenario: Admin attempts user deletion
- **WHEN** an admin user sends DELETE /api/users/{user_id}
- **THEN** the endpoint returns HTTP 501 with detail "User deletion is not yet implemented"

#### Scenario: Non-admin attempts user deletion
- **WHEN** a non-admin user sends DELETE /api/users/{user_id}
- **THEN** the endpoint returns HTTP 501 with detail "User deletion is not yet implemented"

### Requirement: User profile access is self-or-admin
`GET /api/users/{user_id}` SHALL require that the authenticated user's id matches the path `user_id` or that the user is an admin. Non-matching non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: User views own profile
- **WHEN** a non-admin user with id=5 sends GET /api/users/5
- **THEN** the endpoint returns the user with HTTP 200

#### Scenario: User views another profile
- **WHEN** a non-admin user with id=5 sends GET /api/users/7
- **THEN** the endpoint returns HTTP 403 Forbidden

#### Scenario: Admin views any profile
- **WHEN** an admin user sends GET /api/users/7
- **THEN** the endpoint returns the user with HTTP 200

### Requirement: Deployment creation is self-or-admin
`POST /api/users/{user_id}/deployments` SHALL require that the authenticated user's id matches the path `user_id` or that the user is an admin.

#### Scenario: User creates own deployment
- **WHEN** a non-admin user with id=5 sends POST /api/users/5/deployments with a valid payload
- **THEN** the endpoint creates the deployment and returns HTTP 201

#### Scenario: User creates deployment for another user
- **WHEN** a non-admin user with id=5 sends POST /api/users/7/deployments
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Deployment listing is self-or-admin
`GET /api/users/{user_id}/deployments` SHALL require that the authenticated user's id matches the path `user_id` or that the user is an admin.

#### Scenario: User lists own deployments
- **WHEN** a non-admin user with id=5 sends GET /api/users/5/deployments
- **THEN** the endpoint returns the deployments with HTTP 200

#### Scenario: User lists another user's deployments
- **WHEN** a non-admin user with id=5 sends GET /api/users/7/deployments
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Deployment access is self-or-admin
`GET /api/users/{user_id}/deployments/{deployment_id}` SHALL require that the authenticated user's id matches the path `user_id` or that the user is an admin.

#### Scenario: User views own deployment
- **WHEN** a non-admin user with id=5 sends GET /api/users/5/deployments/1
- **THEN** the endpoint returns the deployment with HTTP 200

#### Scenario: User views another user's deployment
- **WHEN** a non-admin user with id=5 sends GET /api/users/7/deployments/1
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Deployment update is self-or-admin
`PUT /api/users/{user_id}/deployments/{deployment_id}` SHALL require that the authenticated user's id matches the path `user_id` or that the user is an admin.

#### Scenario: User updates own deployment
- **WHEN** a non-admin user with id=5 sends PUT /api/users/5/deployments/1 with a valid payload
- **THEN** the endpoint updates the deployment and returns HTTP 200

#### Scenario: User updates another user's deployment
- **WHEN** a non-admin user with id=5 sends PUT /api/users/7/deployments/1
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Deployment deletion is self-or-admin
`DELETE /api/users/{user_id}/deployments/{deployment_id}` SHALL require that the authenticated user's id matches the path `user_id` or that the user is an admin.

#### Scenario: User deletes own deployment
- **WHEN** a non-admin user with id=5 sends DELETE /api/users/5/deployments/1
- **THEN** the endpoint deletes the deployment and returns HTTP 204

#### Scenario: User deletes another user's deployment
- **WHEN** a non-admin user with id=5 sends DELETE /api/users/7/deployments/1
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Session endpoint is unchanged
`GET /api/me` SHALL remain accessible to any authenticated user, returning the authenticated user's own record.

#### Scenario: Any authenticated user accesses /api/me
- **WHEN** any authenticated user sends GET /api/me
- **THEN** the endpoint returns the authenticated user's record with HTTP 200
