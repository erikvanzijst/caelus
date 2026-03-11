## ADDED Requirements

### Requirement: Admin authorization dependency
The system SHALL provide a `require_admin` FastAPI dependency function in `api/app/deps.py` that chains off `get_current_user`. It SHALL raise `HTTPException(status_code=403, detail="Forbidden")` when the authenticated user's `is_admin` field is `False`. It SHALL return the `UserORM` instance when the user is an admin.

#### Scenario: Admin user passes the check
- **WHEN** an admin user (is_admin=True) accesses an endpoint guarded by `require_admin`
- **THEN** the dependency returns the `UserORM` instance and the endpoint executes normally

#### Scenario: Non-admin user is rejected
- **WHEN** a non-admin user (is_admin=False) accesses an endpoint guarded by `require_admin`
- **THEN** the dependency raises HTTP 403 Forbidden with detail "Forbidden"

#### Scenario: Unauthenticated request
- **WHEN** a request without `X-Auth-Request-Email` header accesses an endpoint guarded by `require_admin`
- **THEN** the underlying `get_current_user` dependency rejects the request before `require_admin` is reached

### Requirement: Self-or-admin authorization dependency
The system SHALL provide a `require_self` FastAPI dependency function in `api/app/deps.py` that accepts `user_id: int` (auto-resolved from path parameters) and chains off `get_current_user`. It SHALL raise `HTTPException(status_code=403, detail="Forbidden")` when the authenticated user's `id` does not match `user_id` AND the user is not an admin. It SHALL return the `UserORM` instance when access is allowed.

#### Scenario: User accesses own resource
- **WHEN** a non-admin user with id=5 accesses an endpoint guarded by `require_self` with path parameter user_id=5
- **THEN** the dependency returns the `UserORM` instance and the endpoint executes normally

#### Scenario: User accesses another user's resource
- **WHEN** a non-admin user with id=5 accesses an endpoint guarded by `require_self` with path parameter user_id=7
- **THEN** the dependency raises HTTP 403 Forbidden with detail "Forbidden"

#### Scenario: Admin accesses another user's resource
- **WHEN** an admin user with id=1 accesses an endpoint guarded by `require_self` with path parameter user_id=7
- **THEN** the dependency returns the `UserORM` instance and the endpoint executes normally (admin bypass)
