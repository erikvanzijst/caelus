## Context

The Caelus API is a FastAPI application fronted by oauth2-proxy, which injects `X-Auth-Request-Email` on every request. The existing `get_current_user` dependency in `deps.py` resolves this header to a `UserORM` record (auto-creating if needed), but no endpoint checks `is_admin` or compares `user_id` path parameters to the authenticated user. All authorization is missing.

The `UserORM` model already has an `is_admin: bool` field (defaults to `False`). The service layer is shared between the REST API and a Typer CLI that is used as an admin tool, so authorization checks belong exclusively in the API layer.

## Goals / Non-Goals

**Goals:**
- Enforce least-privilege access on every API endpoint using idiomatic FastAPI dependency injection
- Keep authorization DRY — two reusable dependencies cover all cases
- Maintain admin override — admins can access everything unconditionally
- Disable user deletion until business logic (active deployments, billing) is resolved

**Non-Goals:**
- Role-based access control beyond admin/non-admin (no roles, groups, or permissions tables)
- Authorization in the service layer or CLI
- Changing the authentication mechanism or `get_current_user` auto-create behavior
- Fixing the 404-vs-401 status code for missing auth header (separate concern)
- Implementing user deletion logic

## Decisions

### 1. FastAPI dependencies as authorization guards

**Decision**: Create `require_admin` and `require_self` as FastAPI dependency functions in `deps.py`, chaining off `get_current_user`.

**Rationale**: FastAPI's dependency injection is the idiomatic mechanism for cross-cutting concerns. Dependencies compose naturally (chain via `Depends`), are testable, and FastAPI auto-resolves path parameters for dependencies — so `require_self` can accept `user_id: int` and FastAPI resolves it from the route path without any extra wiring.

**Alternative considered**: Middleware-based approach. Rejected because authorization rules vary per-endpoint (some GETs are open, some are admin-only), which makes middleware too coarse-grained. Per-endpoint dependencies give precise control.

**Alternative considered**: Decorator-based approach (e.g., `@require_admin`). Rejected because FastAPI's dependency system is the established pattern and decorators don't integrate with FastAPI's OpenAPI schema generation or dependency resolution.

### 2. Admin always bypasses self-checks

**Decision**: `require_self` allows access when `current_user.id == user_id` OR `current_user.is_admin`.

**Rationale**: Admins need to manage deployments on behalf of users. Forcing admins to impersonate users would add complexity without benefit.

### 3. Disable user deletion with 501

**Decision**: Replace the `DELETE /api/users/{user_id}` implementation with an `HTTPException(501)` rather than removing the endpoint.

**Rationale**: Keeping the route visible in the OpenAPI schema documents the intent. A 501 clearly communicates "not yet implemented" vs. a 404 which would suggest the endpoint doesn't exist. This prevents someone from re-adding it without considering the business logic constraints.

### 4. HTTP 403 for all authorization failures

**Decision**: Return `403 Forbidden` (not 404) for unauthorized access.

**Rationale**: This is an internal platform behind oauth2-proxy, not a public API. Debuggability outweighs the marginal security benefit of hiding resource existence. All users are already authenticated.

### 5. Authorization only in API layer

**Decision**: No authz in services or CLI.

**Rationale**: The service layer is shared with the CLI, which is an admin-only tool. Adding authz to services would require threading a "caller context" through all service methods, adding complexity with no benefit since the CLI doesn't need access control.

## Risks / Trade-offs

- **[Risk] Auto-created users hit admin-only endpoints and get 403** → Acceptable. The auto-create side effect is harmless, and admin-only endpoints would reject them regardless of creation timing.
- **[Risk] `require_self` depends on FastAPI path parameter name matching** → The dependency parameter must be named `user_id` to match the route's `{user_id}`. This is a naming convention coupling, but it's explicit, documented, and will fail loudly at startup if mismatched.
- **[Trade-off] No fine-grained permissions** → Simple admin/non-admin model. Sufficient for current needs; RBAC can be added later if required without changing the dependency pattern.
