# Issue 011: Deployment Reconciler Core (`DeploymentReconciler.reconcile`)

## Goal
Implement a reconciler abstraction with a small, explicit interface:
1. One class: `DeploymentReconciler`
2. One public method: `reconcile(deployment: DeploymentORM) -> ReconcileResult`

The reconciler must operate only on the provided in-memory deployment state and provisioner calls (no DB reads/writes inside reconciler).

## Depends On
`007-deployment-service-identity-state-and-enqueue.md`
`008-reconcile-job-service.md`
`009-values-merge-and-json-schema-validation.md`
`010-helm-and-kubernetes-adapter-layer.md`

## Scope
Implement in `api/app/services/reconcile.py`:
1. `ReconcileResult` (structured outcome object).
2. `DeploymentReconciler` class with exactly one public method:
   - `reconcile(deployment: DeploymentORM) -> ReconcileResult`
3. Internal helper methods are allowed but should be non-public (underscored), for example:
   - `_validate_input_state(...)`
   - `_resolve_identity(...)`
   - `_build_merged_values(...)`
   - `_reconcile_apply(...)`
   - `_reconcile_delete(...)`

## Input Contract (`reconcile`)
The reconciler receives a fully hydrated `DeploymentORM` object and must not fetch additional DB state.

Required fields/relationships on input:
1. `deployment.desired_template` loaded.
2. `deployment.user` loaded.
3. `deployment.user_values_json` available (may be `None`).
4. `deployment.applied_template` may be `None`.

If required related state is missing, fail fast with a clear error.

## `ReconcileResult` Requirements
Return a structured object that allows the caller (worker/service) to persist state transitions without reconciler DB coupling.

Minimum fields:
1. `status` (target deployment status after reconcile step).
2. `applied_template_id` (optional update when apply succeeds).
3. `last_error` (nullable).
4. `last_reconcile_at` (nullable datetime).

Optional metadata/events payload is allowed for logs/observability.

## Behavior Requirements
1. Enforce template validity from in-memory deployment/template state.
2. Build merged values from `desired_template.default_values_json`, `deployment.user_values_json`, and system overrides.
3. Validate merged values against template schema before applying.
4. Apply path:
   - ensure namespace
   - helm upgrade/install
   - return `ReconcileResult` indicating ready state and applied template update
5. Delete path (triggered by `DeploymentORM.deleted_at` not being `None`):
   - helm uninstall
   - delete namespace
   - return deleted/deleting state accordingly
6. Idempotent behavior for repeated reconcile calls.

## Acceptance Criteria
1. Reconciler has one public entrypoint (`reconcile`).
2. Reconciler contains no direct DB access.
3. Reconciler returns `ReconcileResult` instead of mutating DB.
4. Idempotent repeated calls.

## Test Requirements
1. Unit tests with fake provisioner/adapters for success/failure paths.
2. Tests for input contract failures (missing required loaded relations).
3. Tests for apply/delete idempotence.
4. Tests for `ReconcileResult` correctness:
   - status transitions
   - applied template update
   - error handling behavior
   - reconcile timestamp behavior
