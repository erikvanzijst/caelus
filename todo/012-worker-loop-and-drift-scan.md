# Issue 012: Worker Loop And Drift Scanner Services

## Goal
Implement worker orchestration as thin loop that dequeues from JobService and calls into the DeploymentReconciler.

## Depends On
`008-reconcile-job-service.md`
`011-reconcile-service-core.md`

## Scope

### Worker command
Implement a `worker` cli command that runs a loop of:
1. Dequeue a job: `JobService.claim_next_job()`
2. Reconcile the job: `DeploymentReconciler.reconcile(job)` synchronously
3. Mark the job as done: `JobService.mark_job_done(job)` (or `mark_job_failed`, along with error text)
4. Exit cleanly once the queue is empty or `-n` has been reached (whichever comes first), unless `--follow` is specified.

The command should optionally take the following arguments:
1. `-n`: Maximum number of jobs to process.
2. `--follow`: Continuously poll for new jobs (don't exit).

The worker process should emit reasonable (python) logging to keep the user informed of progress.
The worker process does not require multithreading or multiprocessing. Sequential processing is sufficient.
The output on stdout should be yaml list of jobs that were processed (each finished job printed in realtime, not
batched as a complete list at the end).

### Jobs command
Also implement a `jobs` cli command that lists all `queued` and `running` jobs in the queue in chronological order of
`run_after`. Output should be yaml as with the other cli commands, so it's easy to pipe into other tools or agents.

It should have the following optional arguments:
1. `--failed`: Show only failed jobs
2. `--done`: Show only done jobs
3. `-r`: Reverse `run_after` sort order
4. `--deployment_id`/`-d`: Filter by deployment id


## Behavior Requirements (worker)
1. Worker loop claims one job at a time.
2. On reconcile success, mark done.
3. On reconcile error, mark failed and preserve error text.

## Acceptance Criteria (worker)
1. Loop logic contains no business reconciliation detail.

## Test Requirements (worker)
1. Unit tests for run_worker_once success/failure branches.
2. Test that one failing deployment does not block others.
