## Why

Caelus currently has no concept of pricing, billing, or subscriptions. Users
deploy applications by selecting a product and a template version, but there
is no mechanism to charge for those deployments, offer different tiers of
service (e.g. varying storage or resource limits), or track what a user is
paying for over time. Without a pricing data model, there is no path to
monetization and no way to distinguish free-tier from paid-tier offerings.

This change introduces the foundational pricing and billing data model:
Plans, Plan Template Versions, and Subscriptions. It follows the same
versioning pattern already established by Product / ProductTemplateVersion,
which keeps the conceptual overhead low for developers already familiar with
the codebase.

A critical business requirement drives the design: once a subscription has
been sold to a user at a particular price, subsequent price changes to the
plan must NOT retroactively affect that subscription. This requirement led
to the immutable-template-version pattern, where subscriptions point to the
specific PlanTemplateVersion they were sold under, and price changes are
expressed by creating a new template version rather than mutating an
existing one.

## What Changes

- **New `plan` table**: Represents a named pricing tier for a product (e.g.
  "Basic 50GB", "Pro 500GB"). Each product can have multiple plans. Plans
  follow the same soft-delete pattern as products.
- **New `plan_template_version` table**: Immutable snapshots of a plan's
  commercial terms (price, billing interval, storage quota, description).
  Mirrors the ProductTemplateVersion pattern. A plan's canonical template
  determines what new subscribers see; historical templates are preserved
  for existing subscriptions.
- **New `subscription` table**: Tracks a user's commitment to a specific
  plan template version. Contains lifecycle status (active/cancelled),
  payment status (current/arrears), start date, and external payment
  provider reference. Subscriptions are never soft-deleted -- they are
  permanent historical records.
- **New `subscription_id` FK on `deployment` table**: Every deployment must
  be associated with a subscription (NOT NULL). This means every deployment
  has a clear billing owner and commercial context.
- **Data migration**: Creates a free plan (price_cents=0) per existing
  product, backfills subscriptions for all existing deployments, and wires
  up the new FK -- all in a single Alembic migration.
- **New API endpoints**: RESTful endpoints for browsing plans, managing
  plans (admin), and managing subscriptions. The existing
  `POST /users/{id}/deployments` endpoint is extended to atomically create
  a subscription alongside the deployment.
- **CLI parity**: CLI commands for plan and subscription management matching
  the API endpoints.

## Capabilities

### New Capabilities

- `plan-data-model`: Plan and PlanTemplateVersion ORM models, database
  tables, constraints, and relationships. Mirrors the existing
  Product/ProductTemplateVersion pattern.
- `subscription-data-model`: Subscription ORM model with lifecycle status,
  payment status, and immutable plan template reference. No soft delete.
- `plan-api`: RESTful API endpoints for browsing plans (public) and
  managing plans and plan templates (admin). CLI parity.
- `subscription-api`: RESTful API endpoints for viewing and managing
  subscriptions. CLI parity.
- `deployment-subscription-integration`: Atomic deployment+subscription
  creation, the NOT NULL FK on deployment, and the data migration that
  backfills existing records.

### Modified Capabilities

- `deployment-create-contract`: The deployment creation contract gains a
  required `plan_template_id` field and the response includes the new
  `subscription_id` FK.

## Impact

- **Code**: `api/app/models.py` (new ORM models), `api/app/services/`
  (new service modules for plans and subscriptions, modified deployment
  service), `api/app/api/` (new route modules, modified deployment routes),
  `api/app/cli.py` (new CLI commands).
- **Database**: New tables (`plan`, `plan_template_version`, `subscription`)
  and new column on `deployment` (`subscription_id`). Alembic migration
  with data backfill.
- **Tests**: New test modules for plan and subscription services, API
  endpoints, and CLI commands. Modified deployment tests to include
  subscription creation.
- **UI**: The deployment creation dialog will need to include plan
  selection (out of scope for this change but noted as a downstream
  dependency).
