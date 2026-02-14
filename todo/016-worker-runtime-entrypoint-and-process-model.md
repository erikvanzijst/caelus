# Issue 016: Worker Runtime Entrypoint And Process Model

## Goal
Provide runnable process entrypoint for worker loop and optional drift scan using same codebase image as API.

## Depends On
`012-worker-loop-and-drift-scan.md`
`013-cli-reconcile-command-suite.md`

## Scope
1. Ensure CLI commands can serve as process entrypoint in container:
   - worker loop command
   - drift scan command
2. Add concise operational docs showing process model:
   - `caelus-api` deployment command
   - `caelus-worker` deployment command
   - optional CronJob command for drift scan
3. Add startup logging context (worker id, poll interval, concurrency).

## Acceptance Criteria
1. Worker can run continuously without API server process.
2. Drift scan can run as one-shot command.
3. No code duplication between API and worker logic.

## Test Requirements
1. CLI integration test for one-shot worker command.
2. Smoke test proving command exits cleanly on no-jobs path.
