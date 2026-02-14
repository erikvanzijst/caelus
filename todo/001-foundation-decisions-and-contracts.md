# Issue 001: Foundation Decisions And Contracts

## Goal
Lock down implementation contracts from `k8s/architecture.md` so all later issues share the same assumptions and naming.

## Depends On
None.

## Deliverables
1. A short decision record file at `todo/implementation-contracts.md`.
2. Constants/enums module(s) for statuses/reasons/timeouts.
3. A compatibility section in `api/README.md` describing V1 constraints.

## Required Decisions To Encode
1. Helm-only templates (`package_type = helm-chart`).
2. DB is source of truth.
3. Worker is separate deployment using same codebase.
4. Queue is Postgres table with `SKIP LOCKED`.
5. User-editable values are under `values.user.*` only.
6. `values_schema_json.properties.user` is optional.
7. Admin-only upgrades in V1.
8. Hard delete semantics for deployment deletion.
9. Admin authorization is modeled by `user.is_admin` (Option B).

## Scope
1. Add typed constants module, e.g. `api/app/services/reconcile_constants.py`.
2. Define enums/string constants for:
   - Deployment status (`pending`, `provisioning`, `ready`, `upgrading`, `deleting`, `deleted`, `error`).
   - Job status (`queued`, `running`, `done`, `failed`).
   - Job reason (`create`, `update`, `delete`, `drift`, `retry`).
3. Add naming helper contract:
   - `deployment_uid = {product_slug}-{user_slug}-{suffix6}` with `suffix6 = [0-9a-z]{6}`.
   - DNS-label constraints enforced (lowercase, `[a-z0-9-]`, max 63).
   - truncate base to fit 63-char limit after reserving `-suffix6`.
   - `namespace_name = deployment_uid` in V1.
   - `release_name = deployment_uid` in V1.
4. Document deterministic merge precedence contract for values.

## Acceptance Criteria
1. Later issues can import constants instead of hardcoding status strings.
2. Contracts are documented once and referenced by subsequent issues.
3. `api/README.md` includes a V1 constraints section.

## Test Requirements
1. Unit test verifies status and reason constants are complete and unique.
2. Unit test verifies naming helper output format, DNS-label validity, and max length safety.
3. Unit tests verify naming regex and truncation behavior for long product/email inputs.

## Notes For Next Agent
Use this issue to prevent drift in status/reason vocabulary before migrations and services are implemented.
