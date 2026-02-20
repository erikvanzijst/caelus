# Issue 013: CLI Reconcile Command Suite (Kebab-Case)

## Goal
Add admin-operable CLI commands that mirror worker capabilities and call service-layer functions.

## Depends On
`008-reconcile-job-service.md`
`011-reconcile-service-core.md`
`012-worker-loop-and-drift-scan.md`

## Scope
Update `api/app/cli.py` with commands:
1. `reconcile <deployment-id>`.
2. `enqueue-reconcile <deployment-id> --reason <reason>`.
3. `list-reconcile-jobs [--status ...] [--deployment-id ...]`.
4. `run-worker-once [--worker-id ...]`.
5. `run-worker-loop --concurrency <n> --poll-seconds <n>`.
6. `fail-job <job-id> --error <msg>`.
7. `scan-drift [--drift-age-seconds <n>]`.

## Command Rules
1. Use kebab-case command names only.
2. No direct DB logic in CLI functions; call service methods.
3. Exit codes:
   - `0` success
   - `1` expected operator error (not found/validation)

## Acceptance Criteria
1. Help output includes all new commands.
2. Commands execute against existing session_scope pattern.
3. Output is operator-readable and stable.

## Test Requirements
1. CLI tests for each command happy path.
2. CLI tests for not-found and invalid arguments.
