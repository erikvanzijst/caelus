## 1. Plan Data Model

- [x] 1.1 Create `PlanORM` SQLModel class in `api/app/models.py` with fields: `id`, `product_id` (FK to ProductORM, NOT NULL, indexed), `name` (str), `description` (str, nullable), `template_id` (FK to PlanTemplateVersionORM, nullable), `sort_order` (int, nullable), `created_at`, `deleted_at`. Add partial unique index on `(product_id, lowercase(name))` where `deleted_at IS NULL`.
- [x] 1.2 Create `PlanTemplateVersionORM` SQLModel class in `api/app/models.py` with fields: `id`, `plan_id` (FK to PlanORM, NOT NULL, indexed), `price_cents` (int, NOT NULL), `billing_interval` (enum, NOT NULL -- 'monthly' or 'annual'), `storage_bytes` (int, nullable), `created_at`, `deleted_at`.
- [x] 1.3 Add SQLAlchemy relationships: `PlanORM.templates` (one-to-many), `PlanORM.template` (canonical, via template_id FK), `PlanORM.product` (many-to-one), `ProductORM.plans` (one-to-many), `PlanTemplateVersionORM.plan` (many-to-one).
- [x] 1.4 Create Pydantic read/create/update models: `PlanCreate`, `PlanUpdate`, `PlanRead`, `PlanTemplateVersionCreate`, `PlanTemplateVersionRead`.

## 2. Subscription Data Model

- [x] 2.1 Create `SubscriptionORM` SQLModel class in `api/app/models.py` with fields: `id`, `plan_template_id` (FK to PlanTemplateVersionORM, NOT NULL), `user_id` (FK to UserORM, NOT NULL, indexed), `status` (enum, NOT NULL, default 'active'), `payment_status` (enum, NOT NULL, default 'current'), `cancelled_at` (datetime, nullable), `external_ref` (str, nullable), `created_at`. No `deleted_at` column.
- [x] 2.2 Add SQLAlchemy relationships: `SubscriptionORM.plan_template` (many-to-one to PlanTemplateVersionORM), `SubscriptionORM.user` (many-to-one to UserORM), `SubscriptionORM.deployments` (one-to-many to DeploymentORM), `UserORM.subscriptions` (one-to-many).
- [x] 2.3 Add `subscription_id` FK column to `DeploymentORM` (NOT NULL after migration, FK to SubscriptionORM). Add relationship `DeploymentORM.subscription` (many-to-one).

## 3. Database Migration

- [x] 3.1 Create Alembic migration that creates the `plan`, `plan_template_version`, and `subscription` tables.
- [x] 3.2 In the same migration, for each existing Product: insert a free Plan (`name='Free'`), insert a PlanTemplateVersion (`price_cents=0`, `billing_interval='monthly'`, `storage_bytes=0`), and set the Plan's `template_id` to the new template.
- [x] 3.3 For each existing Deployment: insert a Subscription (`plan_template_id` = free template for that deployment's product, `user_id` = deployment's user_id, `status='active'`, `payment_status='current'`, `created_at` = deployment's created_at).
- [x] 3.4 Add `subscription_id` column to deployment table as nullable, backfill from created subscriptions, then alter to NOT NULL.
- [x] 3.5 Add foreign key constraint on `deployment.subscription_id` referencing `subscription.id`.

## 4. Plan Service Layer

- [x] 4.1 Create `api/app/services/plans.py` with functions: `create_plan()`, `get_plan()`, `list_plans_for_product()`, `update_plan()`, `delete_plan()` (soft delete).
- [x] 4.2 Add plan template functions: `create_plan_template_version()`, `list_plan_template_versions()`.
- [x] 4.3 `list_plans_for_product()` must exclude soft-deleted plans by default. Include canonical template details in the response.

## 5. Subscription Service Layer

- [x] 5.1 Create `api/app/services/subscriptions.py` with functions: `create_subscription()`, `get_subscription()`, `list_subscriptions_for_user()`, `cancel_subscription()`.
- [x] 5.2 `cancel_subscription()` sets `status='cancelled'` and `cancelled_at=utcnow()`. It does not delete the record.
- [x] 5.3 `create_subscription()` validates that the referenced plan_template_id exists and is not soft-deleted.

## 6. Modify Deployment Service

- [x] 6.1 Modify `create_deployment()` in `api/app/services/deployments.py` to accept `plan_template_id`, create a Subscription, and set `deployment.subscription_id` -- all within the existing database transaction.
- [x] 6.2 Validate that `plan_template_id` is provided and references a valid, non-deleted plan template version.
- [x] 6.3 Update `DeploymentCreate` Pydantic model to include `plan_template_id` as a required field.
- [x] 6.4 Update `DeploymentRead` Pydantic model to include `subscription_id`.

## 7. Plan API Endpoints

- [x] 7.1 Create `api/app/api/plans.py` route module.
- [x] 7.2 `GET /products/{product_id}/plans` -- list visible plans for a product (public).
- [x] 7.3 `GET /plans/{plan_id}` -- get a single plan with canonical template details.
- [x] 7.4 `POST /products/{product_id}/plans` -- create a plan (admin only).
- [x] 7.5 `PUT /plans/{plan_id}` -- update plan name, sort_order, or canonical template_id (admin only).
- [x] 7.6 `DELETE /plans/{plan_id}` -- soft-delete a plan (admin only).
- [x] 7.7 `POST /plans/{plan_id}/templates` -- create a new plan template version (admin only).

## 8. Subscription API Endpoints

- [x] 8.1 Create `api/app/api/subscriptions.py` route module.
- [x] 8.2 `GET /users/{user_id}/subscriptions` -- list subscriptions for a user.
- [x] 8.3 `GET /subscriptions/{subscription_id}` -- get a single subscription.
- [x] 8.4 `PUT /subscriptions/{subscription_id}` -- cancel a subscription or update payment status.

## 9. CLI Commands

- [x] 9.1 Add `plan list <product_id>` CLI command.
- [x] 9.2 Add `plan create <product_id>` CLI command (admin).
- [x] 9.3 Add `plan update <plan_id>` CLI command (admin).
- [x] 9.4 Add `plan delete <plan_id>` CLI command (admin).
- [x] 9.5 Add `plan template create <plan_id>` CLI command (admin).
- [x] 9.6 Add `subscription list <user_id>` CLI command.
- [x] 9.7 Add `subscription cancel <subscription_id>` CLI command.
- [x] 9.8 Update `deploy create` CLI command to require `--plan-template-id`.

## 10. Modify Deployment API Endpoint

- [x] 10.1 Update `POST /users/{user_id}/deployments` to accept `plan_template_id` in request body.
- [x] 10.2 Validate `plan_template_id` and return 400 if invalid or missing.
- [x] 10.3 Ensure the deployment response includes `subscription_id`.

## 11. Tests

- [x] 11.1 Plan model tests: create plan, create template version, update canonical template, soft delete plan, verify partial unique index.
- [x] 11.2 Subscription model tests: create subscription, cancel subscription, verify no soft delete column, verify status and payment_status independence.
- [x] 11.3 Plan service tests: CRUD operations, list excluding deleted, canonical template update.
- [x] 11.4 Subscription service tests: create, cancel, list for user, validate plan template reference.
- [x] 11.5 Deployment service tests: verify atomic creation of subscription + deployment, verify subscription_id is set, verify rollback on failure.
- [x] 11.6 Plan API tests: all endpoints, admin authorization, nested routes.
- [x] 11.7 Subscription API tests: all endpoints, user scoping, cancellation.
- [x] 11.8 Deployment API tests: verify plan_template_id is required, verify subscription_id in response, verify 400 on invalid plan_template_id.
- [x] 11.9 Authorization tests: non-admin cannot create/update/delete plans or plan templates. Non-owner cannot GET or PUT subscriptions. Owner can GET and cancel own subscription. Admin can access any subscription.
- [x] 11.10 CLI tests: all new plan and subscription commands, updated deploy create command.
- [ ] 11.11 Migration tests: verify backfill creates correct free plans, subscriptions, and FK linkages. Verify NOT NULL constraint is enforced after migration.
