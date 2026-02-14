# Issue 010: Helm And Kubernetes Adapter Layer

## Goal
Replace stub provisioner path with adapters for namespace lifecycle and Helm release lifecycle.

## Depends On
`001-foundation-decisions-and-contracts.md`
`009-values-merge-and-json-schema-validation.md`

## Scope
Introduce adapter module(s), e.g.:
1. `api/app/services/kube_adapter.py` for namespace operations.
2. `api/app/services/helm_adapter.py` for install/upgrade/uninstall/get status.

## Required Functions
1. `ensure_namespace(name)`.
2. `delete_namespace(name)`.
3. `namespace_exists(name)` and optional `namespace_terminating(name)`.
4. `helm_upgrade_install(release_name, namespace, chart_ref, chart_version, chart_digest, values, timeout, atomic, wait)`.
5. `helm_uninstall(release_name, namespace, timeout, wait)`.
6. `helm_get_release_status(release_name, namespace)`.

## Implementation Notes
1. Keep runtime dependency injection friendly for tests (fake adapters).
2. Start with shelling out to `helm` and `kubectl` or use SDK; keep interface stable.
3. Standardize command error mapping to retryable/fatal categories.

## Acceptance Criteria
1. Adapter methods return structured result objects.
2. Errors include stdout/stderr context safely.
3. No direct adapter calls from API routes; use services only.

## Test Requirements
1. Unit tests with mocked subprocess or fake client.
2. Error mapping tests (retryable vs fatal classification).
