## 1. Worker Process Function

- [x] 1.1 Extract a standalone `_process_one_job(worker_id: str) -> dict | None` function that opens its own `session_scope()`, claims a job, reconciles, marks done/failed, and returns the result dict. This function must be picklable (module-level, no closures).
- [x] 1.2 Use `{base_worker_id}-{os.getpid()}` as the effective `worker_id` inside the pool worker function.

## 2. CLI Options

- [x] 2.1 Add `--concurrency` / `-c` option to the `worker` command (type `int`, default `1`).
- [x] 2.2 Validate that concurrency is >= 1; exit with error otherwise.
- [x] 2.3 Remove the `-n` option from the `worker` command and its associated counting logic.
- [x] 2.4 Remove the `--follow` flag — the worker now polls continuously by default until shutdown.

## 3. Pool Orchestration

- [x] 3.1 When `--concurrency 1`, preserve current sequential behavior (no pool overhead).
- [x] 3.2 When `--concurrency > 1`, create a `ProcessPoolExecutor(max_workers=concurrency)` and submit `_process_one_job` tasks.
- [x] 3.3 Implement the main loop: submit work units up to the concurrency limit, collect results via `as_completed()`, and emit YAML output for each result.
- [x] 3.4 Sleep `--poll-seconds` when no jobs are available, then retry (continuous polling is the default).
- [x] 3.5 Ensure YAML stream items are emitted atomically (no interleaving) — use a lock or serialize output in the main process.

## 4. Graceful Shutdown

- [x] 4.1 Install SIGINT/SIGTERM handlers that set a `threading.Event` (or `multiprocessing.Event`) shutdown flag.
- [x] 4.2 Main loop checks the shutdown flag before submitting new work.
- [x] 4.3 On shutdown, call `executor.shutdown(wait=True)` to drain in-flight jobs, then exit.

## 5. Tests

- [x] 5.1 Test sequential mode (`--concurrency 1`) behaves identically to current behavior.
- [x] 5.2 Test concurrent processing with `--concurrency 4` and multiple queued jobs — verify all jobs are processed and results emitted.
- [x] 5.3 Test that `-n` and `--follow` flags are rejected with errors.
- [x] 5.4 Test `--concurrency 0` exits with an error.
- [x] 5.5 Test graceful shutdown: signal the worker while jobs are in-flight, verify all complete and no jobs are left in `running` state.
