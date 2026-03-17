## Context

Deployment listing is currently user-scoped: `GET /api/users/{user_id}/deployments` returns deployments for a single user. The `list_deployments` service function accepts an optional `user_id` filter but has no status filter, so it returns deleted deployments -- an oversight that the frontend works around by filtering client-side.

The Admin page needs a global view of all active deployments. The dataset is expected to remain small (hundreds, max ~1,000 deployments), so the initial implementation returns the full dataset without pagination or server-side filtering. The admin UI will handle sorting and filtering client-side.

## Goals / Non-Goals

**Goals:**
- Provide an admin-only endpoint that returns all non-deleted deployments using the existing `DeploymentRead` response model.
- Fix the `list_deployments` service to exclude deleted deployments consistently.
- Add a CLI equivalent for listing all deployments as an admin.

**Non-Goals:**
- Pagination (dataset is small enough; will be added later if needed).
- Server-side sorting or filtering (client-side for now).
- New response models or fields (reuse `DeploymentRead` as-is).
- Admin UI for this endpoint (separate change).

## Decisions

### 1. Endpoint path and router placement

**Decision**: Add `GET /api/deployments` as a new route in the existing users router (`api/users.py`), since deployments are closely related to users and the file already contains deployment CRUD routes.

**Why not a separate router**: A single new route doesn't warrant its own router file. The users router already handles deployment operations. If the admin API grows significantly, it can be refactored into a dedicated admin router later.

### 2. Reuse existing service function

**Decision**: Reuse `list_deployments(session, user_id=None)` for the admin endpoint (calling it without `user_id`). Add the deleted-deployment filter to the service function itself so both the user-scoped and admin endpoints benefit.

**Why not a separate admin function**: The only difference between user-scoped and admin listing is the `user_id` filter. The service function already supports `user_id=None` (return all). Adding the status filter there fixes both paths with one change.

### 3. CLI `--all` flag

**Decision**: Add an `--all` flag to the existing `list-deployments` CLI command. When `--all` is provided, skip the `user_id` filter and return deployments for all users. Require that the calling user is an admin (check via `require_admin` on the API, or directly in the CLI if using direct DB access).

**Why not a separate command**: The operation is conceptually the same (list deployments), just with a broader scope. A flag keeps the CLI surface small.

### 4. No pagination design-for-the-future in the response envelope

**Decision**: Return a plain `list[DeploymentRead]` array, not a paginated envelope like `{ items: [...], total: N, cursor: "..." }`. When pagination is added later, the response shape will change.

**Why not future-proof the envelope now**: We have a single internal UI consumer and freedom to make breaking changes. Adding an envelope now would be unnecessary complexity. When pagination is needed, we'll wrap the response and update the UI in one change.

## Risks / Trade-offs

- **Response size**: With ~1,000 deployments, each carrying full template details (including `system_values_json` and `values_schema_json`), the response could reach 3-4 MB. This is acceptable for a PoC but will need pagination or a slimmer response model if the dataset grows significantly.
- **Breaking change when adding pagination**: The flat array response will need to change to a paginated envelope. Since the only consumer is our own UI, this is a low-risk migration.
