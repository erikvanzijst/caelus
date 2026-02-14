# Issue 017: Unit Test Coverage For Reconcile Services And Utilities

## Goal
Add thorough unit tests for all new backend logic before full integration tests.

## Depends On
`006-template-service-v2-and-immutability.md`
`008-reconcile-job-service.md`
`009-values-merge-and-json-schema-validation.md`
`011-reconcile-service-core.md`
`012-worker-loop-and-drift-scan.md`

## Scope
Create/extend test modules under `api/tests/`:
1. `test_template_values.py` for merge/schema validation utilities.
2. `test_reconcile_jobs.py` for queue service methods.
3. `test_reconcile_service.py` with fake adapters.
4. `test_template_v2_service.py` for schema/default/immutability behavior.
5. `test_authz_admin_upgrade.py` for `user.is_admin` authorization paths.

## Coverage Requirements
1. Happy paths.
2. Validation failures.
3. Retryable vs fatal paths.
4. Idempotent repeat reconcile behavior.

## Acceptance Criteria
1. New unit tests pass reliably on sqlite test environment.
2. Existing tests remain green.
3. Postgres-specific queue correctness is covered by dedicated integration test marker/job.
