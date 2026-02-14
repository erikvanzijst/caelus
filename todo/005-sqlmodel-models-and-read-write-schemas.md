# Issue 005: SQLModel And API Schema Expansion

## Goal
Update ORM and pydantic-like read/create/update models to expose new template/deployment fields while preserving compatibility.

## Depends On
`002-alembic-product-template-version-v2-fields.md`
`003-alembic-deployment-v2-fields.md`
`004-alembic-reconcile-job-table.md`

## Scope
Update `api/app/models.py`:
1. Add new fields to `ProductTemplateVersionORM` and corresponding create/read models.
2. Add new fields to `DeploymentORM` and create/read/update models.
3. Add ORM model for `DeploymentReconcileJobORM`.
4. Keep existing relationships functional (`template`, `deployments`, `product`).
5. Add `is_admin: bool = False` to user ORM and read schemas.

## API Payload Model Requirements
1. `ProductTemplateVersionCreate` supports new fields.
2. `DeploymentCreate` supports optional `user_values_json` (or `user_values` alias).
3. Add `DeploymentUpdate` model to support domain change and user values update.
4. Add `DeploymentUpgrade` model for admin-only template changes.

## Validation Constraints
1. `package_type` accepts only `helm-chart`.
2. `deployment_uid`, `namespace_name`, `release_name` immutable once set.
3. `user_values_json` type must be object-like or null.
4. `is_admin` defaults to false and is explicit in admin-seeded users.
5. `deployment_uid`, `namespace_name`, `release_name` must satisfy DNS-label format and length constraints.

## Acceptance Criteria
1. Model metadata aligns with migrated schema.
2. Existing imports and tests compile.

## Test Requirements
1. Unit tests for model validation of new fields.
2. Regression tests for existing old payloads still accepted where compatibility is promised.
