# Monorepo Review Checklist

Use this checklist during review to avoid missing high-risk categories.

## API and Services (`api/`)

- Routes should stay thin; business logic belongs in `api/app/services/`.
- Validate request/response contracts and stable error behavior.
- Ensure ownership boundaries are preserved:
  - templates scoped under products
  - deployments scoped under users
- Check null/empty handling and idempotency for create/update/delete paths.
- Confirm no secrets are hardcoded.

## CLI Parity (`api/app/cli` and services)

- CLI command behavior matches REST behavior for same operation.
- Validations and error semantics are consistent between CLI and API.
- No duplicated business logic in CLI handlers.

## Database and Migrations

- Model/schema changes are paired with Alembic migration updates.
- Migration is reversible or rollback implications are documented.
- Constraints/indexes/defaults align with application assumptions.
- sqlite test behavior does not hide Postgres production issues.

## Provisioning (`api/app/provisioner.py` and callers)

- Failures are handled and surfaced with actionable errors.
- Resource ownership/user scoping is enforced.
- Reconcile/retry behavior avoids duplicate resource creation.

## Testing Expectations

- New behavior has tests at the right layer:
  - API: FastAPI `TestClient`
  - CLI: `typer.testing.CliRunner`
- Regression tests added for bug fixes.
- Boundary and validation cases covered, not just happy paths.

## UI (`ui/`)

- API contract assumptions match backend responses.
- Loading/error/empty states are handled.
- TypeScript types align with API payloads.
- State updates avoid stale data and race-condition regressions.
- User-facing actions with side effects have clear failure messaging.

## Review Red Flags

- Backend behavior changed without corresponding tests.
- API changed but CLI was not updated (or vice versa).
- Model changed without migration.
- Service logic duplicated in route/CLI.
- Silent exception handling or broad `except` with no context.
