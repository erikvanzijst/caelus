# Issue 008: Reconcile Job Service Implementation

## Goal
Implement queue operations in `api/app/services/jobs.py` using DB transactions and `SKIP LOCKED` semantics.

## Depends On
`005-alembic-reconcile-job-table.md`
`002-sqlmodel-models-and-read-write-schemas.md`

## Scope
Create a new service with methods:
1. `enqueue_job(session, deployment_id, reason, run_after=None)`.
2. `list_jobs(session, status=None, deployment_id=None, limit=...)`.
3. `claim_next_job(session, worker_id)`.
4. `mark_job_done(session, job_id)`.
5. `requeue_job(session, job_id, error, delay_seconds)`.
6. `mark_job_failed(session, job_id, error)`.
7. Optional `dedupe_open_jobs(session, deployment_id)` helper.

## Behavior Requirements
1. `claim_next_job` must be concurrency-safe with `FOR UPDATE SKIP LOCKED`.
2. Requeue increments `attempt` and sets `run_after` with backoff.
3. Failed jobs preserve `last_error`.
4. Implement DB-dialect claim strategy:
   - Postgres path uses `FOR UPDATE SKIP LOCKED`.
   - SQLite path uses atomic claim fallback (`UPDATE ... WHERE id=(SELECT ...) ... RETURNING`).

## Acceptance Criteria
1. Multiple concurrent workers can claim distinct jobs.
2. Retry path updates attempt and run_after.
3. Listing supports operator debugging.

## Test Requirements
1. Unit tests for each method.
2. SQLite unit tests for fallback claim path.
3. Postgres integration concurrency test showing no double-claim under parallel workers.
3. Regression test for empty queue behavior.
