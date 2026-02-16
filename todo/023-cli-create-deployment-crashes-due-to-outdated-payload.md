# Issue 023: CLI `create-deployment` Crashes Due To Outdated Payload

## Goal
Make CLI deployment creation functional and aligned with `POST /users/{user_id}/deployments`.

## Problem
CLI constructs `DeploymentCreate` with outdated field `template_id` and passes an unsupported `user_id` kwarg to service call.

## Reproduction
1. `cd api`
2. `uv run --no-sync python -m app.cli create-deployment 1 1 cli-audit.example.test`

## Actual
- Crash: Pydantic validation error requiring `desired_template_id`.
- Exit code: `1`

## Expected
- Command should successfully create deployment when user/template exist.
- Command should map CLI args/options to current `DeploymentCreate` schema.

## Acceptance Criteria
1. CLI uses `desired_template_id` (or maps an alias safely).
2. CLI calls `deployment_service.create_deployment(session, payload=...)` with valid signature.
3. Success path works end-to-end and prints stable output.
