# Issue 012: Worker Loop And Drift Scanner Services

## Goal
Implement worker orchestration as thin loop over job service + reconcile service, and add periodic drift scheduling.

## Depends On
`008-reconcile-job-service.md`
`011-reconcile-service-core.md`

## Scope
Implement in service layer, e.g. `api/app/services/reconcile_runner.py`:
1. `run_worker_once(session, worker_id)`.
2. `run_worker_loop(worker_id, poll_seconds, stop_signal)`.
3. `run_drift_scan(session, drift_age_seconds)`.
4. `enqueue_needed_jobs_for_stuck_or_stale_deployments(...)`.

## Behavior Requirements
1. Worker loop claims one job at a time.
2. On reconcile success, mark done.
3. On retryable error, requeue with backoff.
4. On fatal error, mark failed and preserve error text.
5. Drift scan enqueues:
   - non-deleted deployments with stale reconcile timestamp.
   - deleted deployments not yet in `deleted` status.

## Acceptance Criteria
1. Loop logic contains no business reconciliation detail.
2. Drift scan is safe to run repeatedly.

## Test Requirements
1. Unit tests for run_worker_once success/retry/fatal branches.
2. Unit tests for drift-scan candidate selection.
3. Test that one failing deployment does not block others.
