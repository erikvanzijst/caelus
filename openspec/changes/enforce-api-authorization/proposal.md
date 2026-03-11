## Why

Every API endpoint currently verifies authentication (a valid user exists via `X-Auth-Request-Email`) but never checks *who* the user is or *what* they're allowed to do. Any authenticated user can list all users, modify any user's deployments, or mutate product catalog data. The `is_admin` field on `UserORM` exists but is unused. This needs to be fixed before the platform is used by more than a handful of trusted users.

## What Changes

- Add two reusable FastAPI dependency guards (`require_admin`, `require_self`) in `deps.py` that chain off the existing `get_current_user` dependency.
- Apply `require_admin` to user-management endpoints (`GET/POST /api/users`) and all product/template mutation endpoints (`POST/PUT/DELETE /api/products/**`).
- Apply `require_self` to user-scoped endpoints (`/api/users/{user_id}/**`), allowing access only when `user_id` matches the authenticated user or the user is an admin.
- **Disable** `DELETE /api/users/{user_id}` with HTTP 501 — user deletion has unresolved business logic (active deployments, future billing).
- Product `GET` endpoints remain open to any authenticated user.
- `GET /api/me` remains unchanged.
- Authorization lives only in the API layer; service layer and CLI are unaffected.

## Capabilities

### New Capabilities
- `authorization-guards`: Reusable FastAPI dependency functions (`require_admin`, `require_self`) for endpoint-level authorization
- `user-endpoint-authorization`: Authorization rules applied to user and deployment API endpoints
- `product-endpoint-authorization`: Authorization rules applied to product and template API endpoints
- `authorization-tests`: Parameterized test coverage for the authorization matrix

### Modified Capabilities
<!-- No existing spec-level requirements are changing -->

## Impact

- **Code**: `api/app/deps.py`, `api/app/api/users.py`, `api/app/api/products.py`, test files
- **APIs**: All mutation endpoints now return 403 for unauthorized users. `DELETE /api/users/{user_id}` returns 501. No URL or schema changes.
- **Dependencies**: None — uses existing `is_admin` field and FastAPI dependency injection
- **Systems**: No migrations, no infrastructure changes
