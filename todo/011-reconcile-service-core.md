# Issue 011: Reconcile Service Core (`build_desired_state`, apply, delete)

## Goal
Implement `api/app/services/reconcile.py` core logic matching architecture pseudocode.

## Depends On
`007-deployment-service-identity-state-and-enqueue.md`
`008-reconcile-job-service.md`
`009-values-merge-and-json-schema-validation.md`
`010-helm-and-kubernetes-adapter-layer.md`

## Scope
Implement functions:
1. `build_desired_state(session, deployment_id)`.
2. `reconcile_deployment(session, deployment_id)`.
3. `reconcile_apply(session, desired_state)`.
4. `reconcile_delete(session, deployment)`.
5. `compute_backoff(attempt)` helper.

## `build_desired_state` Requirements
1. Load deployment + desired template.
2. Enforce active template.
3. Ensure identity fields exist or initialize using naming contract:
   - `deployment_uid = {product_slug}-{user_slug}-{suffix6}`.
   - `namespace_name = deployment_uid`.
   - `release_name = deployment_uid`.
4. Build merged values with user scope and system overrides.
5. Validate merged values against full schema.

## `reconcile_apply` Requirements
1. Ensure namespace exists.
2. Run Helm upgrade/install.
3. Update deployment fields:
   - `status=ready`
   - `applied_template_id=desired_template_id`
   - `last_reconcile_at=now`
   - `last_error=null`

## `reconcile_delete` Requirements
1. Helm uninstall.
2. Delete namespace.
3. Retry while namespace terminating.
4. Set `status=deleted` when done.

## Acceptance Criteria
1. Idempotent repeated calls.
2. Handles missing deployment gracefully.
3. Distinguishes retryable and fatal failures.

## Test Requirements
1. Unit tests with fake adapters for success/failure paths.
2. Tests for apply/delete idempotence.
3. Tests for status transitions and applied template updates.
