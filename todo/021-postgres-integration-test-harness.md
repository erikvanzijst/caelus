# Issue 021: Postgres Integration Test Harness For Queue Correctness

## Goal
Add a lightweight Postgres-backed integration test path for queue concurrency semantics that SQLite cannot validate.

## Depends On
`008-reconcile-job-service.md`
`017-unit-tests-for-new-services-and-utils.md`

## Scope
1. Add test harness setup for Postgres integration tests:
   - docker-compose service or testcontainers approach.
   - isolated DB per test session.
2. Add pytest marker `postgres_integration`.
3. Add docs for running locally and in CI.

## Required Tests
1. Parallel worker claim test:
   - enqueue N jobs
   - run M concurrent claim calls
   - assert each job claimed once only.
2. Retry/backoff behavior under concurrent workers.
3. Verify Postgres dequeue path actually uses `FOR UPDATE SKIP LOCKED`.

## Acceptance Criteria
1. Integration tests are optional for fast local runs, required in CI gate for reconcile queue changes.
2. SQLite suite remains fast and green.

## Test Requirements
1. `uv run --no-sync pytest -m \"not postgres_integration\"` for default lightweight run.
2. `uv run --no-sync pytest -m postgres_integration` for queue correctness run.
