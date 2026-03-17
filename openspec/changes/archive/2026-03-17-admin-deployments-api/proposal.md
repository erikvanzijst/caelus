## Why

The Admin page is being extended with a deployments view that shows all deployments across all users. Currently there is no API endpoint that returns deployments globally -- all deployment list endpoints are scoped to a single user (`/api/users/{user_id}/deployments`). Admins need a single endpoint to fetch all active deployments for display in a table with client-side filtering and sorting.

During investigation, we also discovered that the existing user-scoped deployment list endpoint returns deleted deployments. This is inconsistent with the rest of the codebase (unique constraints, hostname checks, and the frontend all treat deleted deployments as hidden) and should be fixed.

## What Changes

- Add a new `GET /api/deployments` endpoint that returns all non-deleted deployments, protected by `require_admin`.
- Fix `list_deployments` service function to exclude deleted deployments, making it consistent with the rest of the codebase.
- Remove the client-side `status !== 'deleted'` filter workaround in `Dashboard.tsx`.
- Add a `list-deployments --all` CLI command for admins to list deployments across all users.

## Capabilities

### New Capabilities
- `admin-list-deployments-endpoint`: Admin-only API endpoint and CLI command for listing all non-deleted deployments across all users.

### Modified Capabilities
- `exclude-deleted-from-list`: Fix the `list_deployments` service to exclude soft-deleted deployments, and remove the client-side workaround.

## Impact

- **API**: New router or route for `GET /api/deployments` with `require_admin` dependency.
- **Service layer**: `list_deployments()` in `deployments.py` gains a `WHERE status != 'deleted'` filter.
- **CLI**: `list-deployments` command gains an `--all` flag (admin-only).
- **UI**: `Dashboard.tsx` removes client-side deleted deployment filter (now handled server-side).
- **Tests**: New tests for the admin endpoint; updated tests for the deleted-deployment exclusion behavior.
- **No data model changes**: No migrations needed.
