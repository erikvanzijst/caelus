# Issue 005: Alembic Migration For Reconcile Job Queue Table

## Goal
Create Postgres-backed queue table for worker orchestration with retry metadata.

## Depends On
`001-foundation-decisions-and-contracts.md`
`002-sqlmodel-models-and-read-write-schemas.md`

## Scope
Create table `deployment_reconcile_job` with fields:
1. `id` (PK).
2. `deployment_id` (FK deployment.id, non-null).
3. `reason` (string enum-like).
4. `status` (string enum-like).
5. `run_after` (datetime, non-null, indexed).
6. `attempt` (int, non-null, default 0).
7. `locked_by` (string nullable).
8. `locked_at` (datetime nullable).
9. `last_error` (text nullable).
10. `created_at` (datetime non-null).
11. `updated_at` (datetime non-null).

Migration authoring flow:
1. First add ORM model for reconcile job table (Issue 002).
2. Generate baseline migration with `alembic revision --autogenerate`.
3. Manually tune indexes/constraints for Postgres and SQLite compatibility.

## Indexes
1. `(status, run_after, id)` for dequeue.
2. `deployment_id` for targeted operations.
3. Optional partial index for queued jobs where `status='queued'` (postgres).

## Queue Safety Rules
1. Multiple queued jobs for same deployment are allowed initially unless dedup strategy is implemented in services.
2. No hard dependency on LISTEN/NOTIFY in schema.
3. Queue schema must support two claim implementations:
   - Postgres: `FOR UPDATE SKIP LOCKED`.
   - SQLite (tests): atomic single-row `UPDATE ... RETURNING` fallback.

## Acceptance Criteria
1. Alembic upgrade adds table and indexes.
2. Downgrade removes cleanly.

## Test Requirements
1. Migration tests verify table structure.
2. SQL smoke test verifies dequeue query can use indexes (explain optional).
