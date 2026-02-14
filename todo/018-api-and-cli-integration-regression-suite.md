# Issue 018: API And CLI Integration Regression Suite

## Goal
Ensure end-to-end parity and prevent regressions across API and CLI with new deployment lifecycle features.

## Depends On
`013-cli-reconcile-command-suite.md`
`014-api-endpoints-for-deployment-update-upgrade-and-status.md`
`017-unit-tests-for-new-services-and-utils.md`

## Scope
1. Expand API flow tests:
   - create template with schema/default values
   - create deployment with user values
   - patch deployment domain/user values
   - request upgrade
   - soft delete deployment and verify delete job queued
2. Expand CLI flow tests for equivalent operations.
3. Add queue visibility assertions in tests where appropriate.
4. Add admin authorization parity checks:
   - admin user can request upgrade
   - non-admin user cannot request upgrade

## Acceptance Criteria
1. API and CLI expose matching capabilities.
2. Test suite verifies key status transitions.
3. Legacy flows still pass.

## Test Requirements
Run full backend suite and ensure deterministic pass:
1. `uv run --no-sync pytest`
2. Add Postgres integration test target (for queue concurrency semantics), e.g. marker:
   - `uv run --no-sync pytest -m postgres_integration`
