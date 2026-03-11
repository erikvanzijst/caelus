## ADDED Requirements

### Requirement: Parameterized authorization test matrix
The test suite SHALL cover the authorization matrix using pytest parameterization to minimize code duplication. The matrix SHALL cover combinations of (endpoint, HTTP method) with user types (admin, self, other_user) and their expected HTTP status codes.

#### Scenario: Test structure uses parameterization
- **WHEN** the authorization tests are implemented
- **THEN** they SHALL use `@pytest.mark.parametrize` to define the test matrix, with each entry specifying the HTTP method, path, user type, expected status code, and request body where applicable

### Requirement: Admin access is tested on all endpoints
The test suite SHALL verify that admin users can access every endpoint unconditionally, including endpoints scoped to other users.

#### Scenario: Admin accesses admin-only endpoint
- **WHEN** tests run for admin-only endpoints (GET/POST /api/users, product mutations) with an admin user
- **THEN** the tests verify HTTP 200/201/204 responses

#### Scenario: Admin accesses another user's scoped endpoint
- **WHEN** tests run for user-scoped endpoints (/api/users/{user_id}/**) with an admin user and a different user_id
- **THEN** the tests verify the admin is granted access (not 403)

### Requirement: Non-admin rejection is tested on admin-only endpoints
The test suite SHALL verify that non-admin users receive HTTP 403 on all admin-only endpoints.

#### Scenario: Non-admin hits admin-only endpoint
- **WHEN** tests run for admin-only endpoints with a non-admin user
- **THEN** the tests verify HTTP 403 Forbidden responses

### Requirement: Self-access is tested on user-scoped endpoints
The test suite SHALL verify that non-admin users can access their own resources but are rejected for other users' resources.

#### Scenario: User accesses own resource
- **WHEN** tests run for user-scoped endpoints with a non-admin user whose id matches the path user_id
- **THEN** the tests verify successful responses (HTTP 200/201/204)

#### Scenario: User accesses another user's resource
- **WHEN** tests run for user-scoped endpoints with a non-admin user whose id does NOT match the path user_id
- **THEN** the tests verify HTTP 403 Forbidden responses

### Requirement: User deletion returns 501
The test suite SHALL verify that `DELETE /api/users/{user_id}` returns HTTP 501 regardless of user type.

#### Scenario: Any user type attempts deletion
- **WHEN** tests run for DELETE /api/users/{user_id} with admin, self, and other user types
- **THEN** the tests verify HTTP 501 Not Implemented responses for all cases
