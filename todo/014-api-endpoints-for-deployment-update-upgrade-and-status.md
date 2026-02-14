# Issue 014: API Endpoints For Deployment Update, Upgrade, And Status Fields

## Goal
Expose new deployment lifecycle operations and fields through REST API with parity to CLI/service behavior.

## Depends On
`007-deployment-service-identity-state-and-enqueue.md`
`011-reconcile-service-core.md`

## Scope
Update `api/app/api/users.py` and related schemas/services:
1. Add endpoint to update deployment runtime config (domain and user values), e.g.:
   - `PATCH /users/{user_id}/deployments/{deployment_id}`
2. Add endpoint for admin-triggered upgrade request, e.g.:
   - `POST /users/{user_id}/deployments/{deployment_id}/upgrade`
3. Ensure list/get responses include status fields:
   - `status`, `desired_template_id`, `applied_template_id`, `last_error`, `last_reconcile_at`, `generation`.

## Behavior Requirements
1. Update endpoint enqueues reconcile update job.
2. Upgrade endpoint enqueues reconcile update job and sets `desired_template_id`.
3. Validate template existence and compatibility before accepting upgrade.
4. Keep delete endpoint behavior as soft-delete + enqueue delete job.
5. Enforce admin-only upgrade authorization using `user.is_admin`.

## Acceptance Criteria
1. API and CLI support same operations and validations.
2. API errors are stable and documented.

## Test Requirements
1. API tests for update, upgrade, and status fields.
2. API tests for invalid user values and invalid template ids.
3. Regression tests for existing endpoints.
4. API tests verify non-admin cannot trigger upgrade (403/401 according to API convention).
