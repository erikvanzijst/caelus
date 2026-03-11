## Why

Caelus now has a real identity stack (Keycloak + oauth2-proxy) injecting `X-Auth-Request-Email` into upstream requests, but the application ignores it entirely. API endpoints accept anonymous requests, the frontend fakes authentication by asking the user to type an email, and user creation is a client-side concern. We need the backend to own authentication so that every endpoint knows which user is making the request — a prerequisite for authorization, audit logging, and any future per-user behavior.

## What Changes

- Add `GET /api/me` endpoint that reads the `X-Auth-Request-Email` header, looks up (or auto-creates) the corresponding user, and returns a `UserRead`. Returns `404` when the header is absent.
- Add a FastAPI dependency `get_current_user` that resolves `X-Auth-Request-Email` to a `UserORM` with auto-creation for unknown emails. Inject this dependency into all existing API endpoint functions as plumbing for future authorization.
- Add CLI authentication via `CAELUS_USER_EMAIL` environment variable with an optional `--as-user` override flag. The CLI resolves the email to a user through the same lookup/auto-create logic.
- Simplify the frontend startup flow: hit `GET /api/me`, proceed on `200`, show an email dialog on `404` (local-dev mode). Store extra request headers in localStorage; in production this stays empty (oauth2-proxy provides the header at the proxy layer), in local-dev it gets populated with `X-Auth-Request-Email` after the dialog.
- Remove the "Switch user" button from the AppShell.
- Remove client-side user auto-creation logic from the Dashboard.

## Capabilities

### New Capabilities
- `session-authentication`: Backend authentication via `X-Auth-Request-Email` header, `GET /api/me` endpoint, `get_current_user` FastAPI dependency injection into all endpoints, and CLI authentication via environment variable.
- `local-dev-auth-fallback`: Frontend email dialog for local development when no auth proxy is present, with transparent header injection so backend behavior is identical across environments.

### Modified Capabilities
- None.

## Impact

- Affected API code: `api/app/api/users.py` (new `/me` endpoint), new `api/app/deps.py` or similar (auth dependency), all route modules (dependency injection added to endpoint signatures).
- Affected CLI code: `api/app/cli.py` (env var reading, `--as-user` flag).
- Affected UI code: `ui/src/api/client.ts` (header injection from localStorage), `ui/src/components/EmailDialog.tsx` (trigger logic), `ui/src/components/AppShell.tsx` (remove Switch button, startup flow), `ui/src/pages/Dashboard.tsx` (remove client-side user creation), `ui/src/state/useAuthEmail.ts` (refactor to header-based state).
- No database schema changes or Alembic migrations required.
- Tests required across API (dependency, `/me` endpoint, header enforcement), CLI (env var and override), and UI (startup flow, dialog behavior).
