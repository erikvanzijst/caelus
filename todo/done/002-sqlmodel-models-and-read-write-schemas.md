# Issue 002: SQLModel And API Schema Expansion

## Goal
Update ORM and pydantic-like read/create/update models to expose new template/deployment fields while preserving compatibility.

## Depends On
`001-foundation-decisions-and-contracts.md`

## Scope
Update `api/app/models.py`:
1. Add the following fields to `ProductTemplateVersionORM` (in addition to existing fields):
   - `version_label` (nullable string)
   - `package_type` (string, V1 allowed value `helm-chart`)
   - `chart_ref` (nullable string)
   - `chart_version` (nullable string)
   - `chart_digest` (nullable string)
   - `default_values_json` (json/text)
   - `values_schema_json` (json/text)
   - `capabilities_json` (json/text, optional)
   - `health_timeout_sec` (nullable int)
2. Keep `docker_image_url` for compatibility during rollout.
3. Add the following fields to `DeploymentORM` (in addition to existing fields):
   - `deployment_uid` (immutable slug id)
   - `namespace_name`
   - `release_name`
   - `desired_template_id` (FK to `product_template_version.id`)
   - `applied_template_id` (FK to `product_template_version.id`, nullable)
   - `user_values_json` (json/text, nullable)
   - `status`
   - `generation`
   - `last_error` (nullable text)
   - `last_reconcile_at` (nullable datetime)
4. Add `is_admin: bool = False` to user ORM and read schemas.
5. Add ORM model for `DeploymentReconcileJobORM` with fields:
   - `id`
   - `deployment_id` (FK)
   - `reason`
   - `status`
   - `run_after`
   - `attempt`
   - `locked_by` (nullable)
   - `locked_at` (nullable)
   - `last_error` (nullable)
   - `created_at`
   - `updated_at`
6. Keep existing relationships functional (`template`, `deployments`, `product`).

## API Payload Model Requirements
1. `ProductTemplateVersionCreate` supports:
   - `version_label`, `package_type`, `chart_ref`, `chart_version`, `chart_digest`,
     `default_values_json`, `values_schema_json`, `capabilities_json`, `health_timeout_sec`
   - plus compatibility field `docker_image_url` during rollout
2. `ProductTemplateVersionRead` includes all persisted template fields above.
3. `DeploymentCreate` supports optional `user_values_json` (or `user_values` alias).
4. Add `DeploymentUpdate` model to support domain change and user values update.
5. Add `DeploymentUpgrade` model for admin-only template changes.
6. `DeploymentRead` includes new reconciliation state fields:
   - `deployment_uid`, `namespace_name`, `release_name`
   - `desired_template_id`, `applied_template_id`
   - `status`, `generation`, `last_error`, `last_reconcile_at`

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
