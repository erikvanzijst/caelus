## ADDED Requirements

### Requirement: Concurrency option
The `worker` CLI command SHALL accept a `--concurrency` / `-c` option that specifies the maximum number of jobs to process in parallel. The default value SHALL be `1`.

#### Scenario: Default concurrency
- **WHEN** the worker is started without `--concurrency`
- **THEN** jobs SHALL be processed one at a time (sequential behavior, identical to current implementation)

#### Scenario: Explicit concurrency
- **WHEN** the worker is started with `--concurrency 4`
- **THEN** up to 4 jobs SHALL be processed simultaneously

#### Scenario: Concurrency validation
- **WHEN** the worker is started with `--concurrency 0` or a negative value
- **THEN** the CLI SHALL exit with an error message

### Requirement: Process pool lifecycle
The worker SHALL use a `concurrent.futures.ProcessPoolExecutor` to manage parallel job processing. Each pool worker process SHALL create its own database session.

#### Scenario: Pool worker isolation
- **WHEN** multiple jobs are processed concurrently
- **THEN** each job SHALL be claimed, reconciled, and marked done/failed within its own independent database session

#### Scenario: Pool worker identification
- **WHEN** a pool worker claims a job
- **THEN** the `locked_by` field SHALL be set to `{base_worker_id}-{pid}` where `pid` is the process ID of the pool worker

### Requirement: Remove -n flag
The `worker` CLI command SHALL remove the `-n` option.

#### Scenario: -n flag rejected
- **WHEN** the worker is started with `-n 10`
- **THEN** the CLI SHALL exit with an error indicating that `-n` is no longer supported

### Requirement: Remove --follow flag
The `worker` CLI command SHALL remove the `--follow` flag. The worker SHALL poll continuously by default until terminated by a signal.

#### Scenario: --follow flag rejected
- **WHEN** the worker is started with `--follow`
- **THEN** the CLI SHALL exit with an error indicating that `--follow` is no longer supported

### Requirement: Continuous polling
The worker SHALL continuously poll for new jobs, sleeping `--poll-seconds` between attempts when no jobs are available, until a shutdown signal is received.

#### Scenario: Idle polling
- **WHEN** the job queue is empty
- **THEN** the worker SHALL sleep for `--poll-seconds` and then attempt to claim again

#### Scenario: Saturation with concurrency
- **WHEN** the worker is started with `--concurrency 4`
- **AND** 4 jobs are currently in-flight
- **THEN** the worker SHALL wait for at least one job to complete before claiming more

### Requirement: Graceful shutdown
The worker SHALL handle SIGINT and SIGTERM signals gracefully when running with concurrency > 1.

#### Scenario: Shutdown signal received
- **WHEN** a SIGINT or SIGTERM signal is received
- **THEN** the worker SHALL stop claiming new jobs
- **AND** wait for all in-flight jobs to finish
- **AND** exit cleanly

#### Scenario: No orphaned running jobs on clean shutdown
- **WHEN** a shutdown signal is received and in-flight jobs complete
- **THEN** all jobs SHALL be in a terminal state (`done` or `failed`), not `running`

### Requirement: YAML output with concurrency
The worker SHALL continue to emit YAML stream items for each completed job, regardless of concurrency level.

#### Scenario: Output ordering
- **WHEN** multiple jobs complete concurrently
- **THEN** each job result SHALL be emitted as a complete YAML stream item
- **AND** items SHALL NOT be interleaved (each item is atomic)
