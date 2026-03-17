## Why

The `cli:worker` command processes deployment reconciliation jobs sequentially — one job at a time per worker instance. When many deployments need reconciliation simultaneously (e.g., bulk creates or updates), jobs queue up and wait. Adding a process pool allows a single worker instance to reconcile multiple deployments in parallel, reducing end-to-end latency for queued jobs without requiring additional worker pods.

## What Changes

- Add a `--concurrency` / `-c` option to the `worker` CLI command (default `1` to preserve current behavior).
- Implement a `multiprocessing`-based process pool that claims and processes up to `concurrency` jobs simultaneously.
- Each pool worker gets its own database session (required since SQLAlchemy sessions are not thread/process-safe).
- Graceful shutdown: on SIGINT/SIGTERM, stop claiming new jobs and wait for in-flight jobs to finish.
- **BREAKING**: Remove the `-n` (max jobs) option — it adds cross-worker accounting complexity and has no production use case.
- **BREAKING**: Remove the `--follow` flag — the worker now polls continuously by default until shut down via signal. The `--poll-seconds` option is retained to control the polling interval.

## Capabilities

### New Capabilities
- `worker-process-pool`: Parallel job processing via a configurable process pool in the `worker` CLI command.

### Modified Capabilities

_(none — no existing spec-level requirements change)_

## Impact

- **Code**: `api/app/cli.py` (worker command), potentially a new module for pool orchestration logic.
- **Dependencies**: Uses Python stdlib `multiprocessing` / `concurrent.futures` — no new packages.
- **Database**: No schema changes. Existing `FOR UPDATE SKIP LOCKED` (Postgres) and atomic claim (SQLite) already support concurrent claiming safely.
- **Tests**: New tests for parallel job processing, graceful shutdown, and concurrency limits.
- **Terraform**: The worker deployment may expose `CAELUS_WORKER_CONCURRENCY` as a configurable env var.
