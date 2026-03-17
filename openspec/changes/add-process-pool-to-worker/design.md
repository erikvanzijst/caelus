## Context

The `worker` CLI command (`api/app/cli.py:550`) processes deployment reconciliation jobs in a sequential loop. It calls `_run_worker_once()` which claims one job via `JobService.claim_next_job()`, reconciles it, marks it done/failed, and repeats. The database layer already supports safe concurrent claiming — Postgres uses `FOR UPDATE SKIP LOCKED` and SQLite uses atomic `UPDATE...RETURNING`. However, a single worker instance can only process one job at a time.

In production (Kubernetes), scaling requires deploying additional worker pods. A process pool within a single worker allows utilizing multiple CPU cores without additional pods, reducing latency when many jobs are queued.

## Goals / Non-Goals

**Goals:**
- Allow the `worker` command to process multiple jobs concurrently via a `--concurrency` option.
- Preserve backward compatibility: `--concurrency 1` (default) behaves identically to current sequential mode.
- Handle graceful shutdown (SIGINT/SIGTERM) — stop claiming, drain in-flight jobs.
- Remove the `-n` flag to simplify the orchestration loop (no cross-worker job accounting needed).
- Remove the `--follow` flag — the worker polls continuously until signaled to stop. This is the only production-relevant mode.

**Non-Goals:**
- Async/await rewrite — the reconciler and provisioner are synchronous, so processes/threads are appropriate.
- Job retry logic — out of scope (failed jobs remain terminal).
- Dynamic concurrency adjustment at runtime.
- Changes to the database schema or job claiming logic.

## Decisions

### 1. `concurrent.futures.ProcessPoolExecutor` over `multiprocessing.Pool` or threads

**Choice**: Use `concurrent.futures.ProcessPoolExecutor`.

**Rationale**: `concurrent.futures` provides a clean `Future`-based API with `as_completed()` for tracking results. `ProcessPoolExecutor` avoids GIL contention (reconciliation may involve CPU-bound Helm template rendering). Threads would work for I/O-bound work but processes are safer given the provisioner may do heavy work.

**Alternative considered**: `multiprocessing.Pool` — lower-level API, harder to integrate with shutdown signals. `ThreadPoolExecutor` — simpler but subject to GIL; acceptable fallback if process serialization proves problematic.

### 2. Each subprocess gets its own database session

**Choice**: Create a fresh `Session` inside each worker process function, not passed from the parent.

**Rationale**: SQLAlchemy `Session` and `Engine` objects are not safe to share across process boundaries. Each process function will call `session_scope()` independently. This matches how the existing test suite (`test_jobs_service_postgres.py`) already uses `ThreadPoolExecutor` with per-thread sessions.

### 3. Orchestration loop in the main process

**Choice**: The main process runs the claim-dispatch loop. It claims jobs and submits them to the pool. The pool workers receive a `job_id` and `worker_id`, open their own session, and run reconciliation.

**Rationale**: Claiming in the main process keeps the concurrency control simple — the main loop can track how many futures are in-flight and stop submitting when at the concurrency limit or when `-n` is reached. This avoids each subprocess independently polling, which would complicate shutdown and counting.

**Revised approach**: Actually, having each pool worker claim its own job is simpler and more robust — it avoids serializing the claimed job object across process boundaries and keeps the claim→reconcile→mark-done lifecycle atomic within one process. The main process simply submits "go claim and process a job" tasks and tracks completions.

**Final choice**: Pool workers claim their own jobs. The main process submits work units and manages the concurrency window. With the `-n` flag removed, the main process only needs to track in-flight futures for the concurrency cap and shutdown — no cross-process counting.

### 4. Signal handling for graceful shutdown

**Choice**: Install SIGINT/SIGTERM handlers in the main process that set a `shutdown` event. The main loop checks this event before submitting new work. `ProcessPoolExecutor.shutdown(wait=True)` drains in-flight jobs.

**Rationale**: Workers should finish their current reconciliation (which commits status to DB) rather than being killed mid-operation, which would leave jobs in `running` state indefinitely.

### 5. Worker ID scheme for pool processes

**Choice**: Each pool process uses `{worker_id}-{pid}` as its effective worker ID (where `worker_id` is the base ID from env/CLI and `pid` is `os.getpid()`).

**Rationale**: The `locked_by` field in the job table identifies which worker holds a job. With multiple processes, each needs a unique identifier for debugging and stale-lock detection.

## Risks / Trade-offs

- **SQLite concurrency limits** → SQLite has coarse-grained locking; concurrent writers may see `database is locked` errors. Mitigation: With `--concurrency 1` as default, SQLite users are unaffected. Document that higher concurrency requires Postgres.
- **Process startup overhead** → Spawning processes has higher latency than threads. Mitigation: `ProcessPoolExecutor` reuses workers across jobs; the pool is created once.
- **Orphaned running jobs** → If a worker process is killed (OOM, etc.), its job stays `running`. Mitigation: This is an existing limitation (same as current single-process mode). A future stale-job reaper could address this.
- **Serialization constraints** → Process pool workers can't share in-memory state with the parent. Mitigation: Workers are self-contained — they claim, reconcile, and mark done independently, returning only a small result dict.
