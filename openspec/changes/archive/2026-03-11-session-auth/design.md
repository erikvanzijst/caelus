## Context

Caelus recently gained a Keycloak identity provider with oauth2-proxy injecting `X-Auth-Request-Email` into requests at the reverse proxy layer. However, the application has no server-side authentication: API endpoints are fully anonymous, the frontend stores a self-reported email in localStorage and sends it as a header the backend ignores, and user creation is triggered client-side on the Dashboard. This change wires authentication through the backend so every endpoint knows the current user, without yet adding authorization (checking what the user is allowed to do).

Constraints and inputs for this design:
- Authentication only, not authorization. No access control checks in this change.
- Email addresses are immutable and uniquely identify users forever.
- `X-Auth-Request-User` header is ignored; only `X-Auth-Request-Email` is used.
- No database schema changes — the existing User model with integer PK, email column, and partial unique index is sufficient.
- Backend behavior must be identical regardless of whether the email comes from oauth2-proxy (production) or the frontend (local dev).
- Network topology (Traefik → oauth2-proxy → API) guarantees header authenticity in production; the application trusts the header unconditionally.

## Goals / Non-Goals

**Goals:**
- Add `GET /api/me` that returns the authenticated user or `404` when no auth header is present.
- Add a `get_current_user` FastAPI dependency that resolves `X-Auth-Request-Email` to a `UserORM`, auto-creating new users on first encounter.
- Inject `get_current_user` into all existing endpoint functions as plumbing.
- Add CLI authentication via `CAELUS_USER_EMAIL` env var with optional `--as-user` override.
- Simplify frontend to use `GET /api/me` for session initialization and show email dialog only on `404`.
- Remove "Switch user" button and client-side user creation from Dashboard.

**Non-Goals:**
- Authorization (asserting `user_id` in URL matches authenticated user).
- Threading an `actor` parameter through service layer methods.
- Database schema changes or Alembic migrations.
- NetworkPolicy hardening of Kubernetes namespaces.
- Admin-specific endpoints or role-based access.

## Decisions

1. Keep integer user IDs in API URL paths.
- Rationale: clean URLs with no encoding issues, existing code and data model work as-is, no migration needed. The lookup from email to integer ID happens once on session init via `/api/me`.
- Alternative considered: use email in URLs; rejected due to percent-encoding pain (`@` → `%40`, potential unicode) and email leakage in URLs.
- Alternative considered: use hash of email in URLs; rejected because it still requires a server lookup (no better than integer ID) while being longer, opaque, and less human-readable.
- Alternative considered: implicit `/api/me/deployments` style URLs to avoid user ID entirely; rejected because explicit user-keyed URLs are still needed for admin use cases, so implicit paths would add a second set of routes without eliminating the first.

2. Backend reads and trusts `X-Auth-Request-Email` unconditionally — no mode switching.
- Rationale: in production, oauth2-proxy guarantees the header is authentic. In local dev, self-reported email is acceptable. The backend behaves identically in both environments, minimizing moving parts.
- Alternative considered: server-side env var to toggle between "trust header" and "reject if no proxy" modes; rejected because the trust model is already enforced by network topology and an env var adds complexity without security benefit.

3. `GET /api/me` returns `404` (not `401`) when `X-Auth-Request-Email` header is absent.
- Rationale: the Traefik `oauth-errors` middleware intercepts `401` responses and translates them to `302` redirects to Keycloak. A `401` from the API could inadvertently trigger the OAuth login dance during local development. `404` is semantically defensible ("there is no 'me' in this request context") and avoids interference with the auth infrastructure.
- Alternative considered: return `401`; rejected due to Traefik middleware interception risk in mixed environments.

4. Auto-create user records on first encounter of an unknown email.
- Rationale: since Keycloak is authoritative for identity, any email that reaches the API through the header is a legitimate user. Requiring pre-registration adds friction with no security benefit. This also matches the current client-side behavior where the Dashboard auto-creates users.
- Alternative considered: require explicit user creation via admin endpoint; rejected because it adds an onboarding step with no value when Keycloak has already authenticated the user.

5. Frontend stores extra request headers in localStorage, applied unconditionally to all API calls.
- Rationale: in production, this object is empty (oauth2-proxy injects the header at the proxy layer, invisible to browser JS). In local dev, it contains `{"X-Auth-Request-Email": "user@example.com"}` after the email dialog. One code path for making API requests regardless of environment.
- Alternative considered: conditionally add header based on detected auth mode; rejected because the unconditional approach is simpler and mode detection is unnecessary.

6. `GET /api/me` is the sole session initialization mechanism.
- Rationale: the frontend hits `/api/me` on startup. A `200` means we're authenticated (user object returned). A `404` means no header present — show the email dialog (local-dev). This eliminates the need for `GET /api/users` + find-by-email + conditional `POST /api/users` that the Dashboard does today.
- Alternative considered: separate `/api/config` endpoint to report auth mode; rejected because the `/api/me` response already encodes everything the frontend needs.

7. CLI authenticates via `CAELUS_USER_EMAIL` environment variable with optional `--as-user` flag override.
- Rationale: standard Unix pattern (analogous to `AWS_PROFILE`, `GITHUB_TOKEN`). Avoids cluttering every command with `--email`, avoids stateful session files.
- Alternative considered: required `--email` flag on every command; rejected as noisy and repetitive.
- Alternative considered: `login` command writing a session file; rejected for introducing external state management.

8. Remove the "Switch user" button from AppShell.
- Rationale: in production, identity comes from Keycloak and cannot be switched client-side. In local dev, clearing localStorage achieves the same effect. The button is a relic of the old fake-auth model.

## Risks / Trade-offs

- [Auto-create could accumulate stale user records from one-time visitors] → Acceptable; user records are lightweight and soft-deletable. A cleanup mechanism can be added later if needed.
- [Frontend localStorage headers could be stale after browser restarts in local dev] → Acceptable; the email dialog reappears if `/api/me` returns `404`, naturally refreshing the stored headers.
- [Trusting X-Auth-Request-Email unconditionally means internal network access could impersonate users] → Accepted risk; mitigated by Kubernetes network topology and future NetworkPolicies (out of scope for this change).
- [404 from /api/me is non-standard for "unauthenticated"] → Documented design decision with clear rationale; the alternative (401) has worse operational consequences.

## Migration Plan

1. Add `get_current_user` FastAPI dependency that reads `X-Auth-Request-Email`, performs case-insensitive user lookup, auto-creates if not found, returns `UserORM`.
2. Add `GET /api/me` endpoint using the dependency, returning `UserRead` or `404`.
3. Inject `get_current_user` dependency into all existing endpoint functions (no behavioral change yet — just wiring).
4. Add CLI `CAELUS_USER_EMAIL` env var reading and `--as-user` override with same lookup/auto-create logic.
5. Refactor frontend: replace Dashboard user-creation flow with `/api/me` startup, refactor header injection to use localStorage headers object, update email dialog trigger to `/api/me` 404 response.
6. Remove "Switch user" button from AppShell.
7. Add tests across API, CLI, and UI for new authentication flows.

Rollback:
- Remove `get_current_user` dependency from endpoint signatures.
- Remove `/api/me` endpoint.
- Revert frontend to prior localStorage email + client-side user creation flow.
- No database rollback needed (no schema changes).

## Open Questions

- None for this proposal phase.
