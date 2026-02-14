# Issue 003: Alembic Migration For Deployment V2 Fields

## Goal
Add identity, desired/applied template tracking, status, and user values storage for reconciliation.

## Depends On
`001-foundation-decisions-and-contracts.md`

## Scope
Add migration columns to `deployment`:
1. `deployment_uid` (string slug id, unique, nullable for backfill then non-null).
2. `namespace_name` (string, unique among active rows or globally unique).
3. `release_name` (string).
4. `desired_template_id` (FK to `product_template_version.id`, nullable for backfill then non-null).
5. `applied_template_id` (FK to `product_template_version.id`, nullable).
6. `user_values_json` (JSON/text, nullable).
7. `status` (string, default `pending`).
8. `generation` (int, default `1`).
9. `last_error` (text, nullable).
10. `last_reconcile_at` (datetime, nullable).

Also add to `user`:
1. `is_admin` (boolean, non-null, default `false`).

## Backfill Rules
1. `deployment_uid` generated with naming helper:
   - `{product_slug}-{user_slug}-{suffix6}`.
   - `suffix6` random base36.
   - DNS-label safe and max length 63.
2. `namespace_name = deployment_uid`.
3. `release_name = deployment_uid`.
4. `desired_template_id = template_id` for existing rows.
5. `status = pending` for existing active rows.

## Constraints
1. Keep domainname mutable; do not use as identity.
2. Add indexes for `status`, `desired_template_id`, `applied_template_id`, `deployment_uid`.
3. `is_admin` is the sole V1 authorization flag for admin-only operations.
4. `deployment_uid` must match regex `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` and length <= 63.

## Acceptance Criteria
1. Migration upgrade and downgrade run cleanly.
2. Existing deployment rows are backfilled with valid identity and desired template linkage.
3. No foreign key breakage on soft deletes.

## Test Requirements
1. Migration test with pre-existing deployment row verifies backfill values.
2. Migration test verifies uniqueness constraints on `deployment_uid` and namespace policy.
3. Migration test verifies `user.is_admin` defaults to false.
4. Migration test verifies backfilled `namespace_name == deployment_uid` and `release_name == deployment_uid`.
