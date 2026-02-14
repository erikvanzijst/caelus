# Issue 002: Alembic Migration For ProductTemplateVersion V2 Fields

## Goal
Expand `product_template_version` from `docker_image_url`-only to immutable Helm template metadata plus schema/default values.

## Depends On
`001-foundation-decisions-and-contracts.md`

## Scope
Add a new Alembic migration after current head with columns on `product_template_version`:
1. `version_label` (nullable string initially).
2. `package_type` (string, default `helm-chart`, non-null after backfill).
3. `chart_ref` (nullable string).
4. `chart_version` (nullable string).
5. `chart_digest` (nullable string).
6. `default_values_json` (JSON/text type compatible with sqlite+postgres).
7. `values_schema_json` (JSON/text type compatible with sqlite+postgres).
8. `capabilities_json` (JSON/text, optional in V1).
9. `health_timeout_sec` (int, nullable with default fallback in code).

## Migration Details
1. Keep existing `docker_image_url` for backward compatibility during rollout.
2. Backfill `package_type = helm-chart` for existing rows.
3. Add check constraint for `package_type` allowed set (at least `helm-chart`).
4. Add index strategy for lookups by `product_id` and `deleted_at` remains intact.

## Data Compatibility
1. Existing test data must continue to load.
2. Existing API calls creating templates with old payload should still function until API issue introduces required new fields.

## Acceptance Criteria
1. Alembic upgrade/downgrade works cleanly.
2. `pytest` migrations tests or equivalent smoke checks pass for sqlite test DB.
3. New columns appear in SQLModel metadata after model updates (Issue 005).

## Test Requirements
1. Add migration test verifying new columns exist.
2. Add downgrade test for schema rollback.

## Notes For Next Agent
Do not remove legacy field yet; deprecation/removal should be a later controlled change after API and UI are migrated.
