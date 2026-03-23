## Context

Caelus models products and their deployable configurations as two separate
entities: `ProductORM` (identity, name, description) and
`ProductTemplateVersionORM` (versioned technical configuration -- chart
reference, values schema, capabilities). A product's "current" configuration
is determined by a canonical `template_id` FK on the product record. When
the configuration changes, a new template version is created and the
canonical FK is updated. Existing deployments that reference an older
template version are unaffected. This pattern provides immutable versioning
with atomic switchover.

The current entity relationships:

```
+-------------+        +---------------------------+
| ProductORM  |--1:N-->| ProductTemplateVersionORM |
|             |        |                           |
| id          |        | id                        |
| name        |        | product_id (FK)           |
| description |        | chart_ref                 |
| template_id |<--ref--| chart_version             |
|  (canonical)|        | system_values_json        |
| created_at  |        | values_schema_json        |
| deleted_at  |        | capabilities_json         |
+-------------+        | health_timeout_sec        |
                       | created_at                |
                       | deleted_at                |
                       +---------------------------+
                                   |
                              N:1  |  desired_template_id
                                   v
                       +---------------------------+
                       |     DeploymentORM         |
                       |                           |
                       | id                        |
                       | user_id (FK)              |
                       | desired_template_id (FK)  |
                       | applied_template_id (FK)  |
                       | hostname                  |
                       | name, namespace            |
                       | user_values_json          |
                       | status                    |
                       | created_at                |
                       | deleted_at                |
                       +---------------------------+
```

There is no pricing, billing, or subscription system. A standalone Streamlit
pricing calculator exists in `products/pricing/pricing_model.py` but it is
purely analytical and not integrated with the database or API.

The existing codebase uses these patterns consistently:
- Soft deletes via `deleted_at` nullable timestamp
- Partial unique indexes that exclude soft-deleted rows
- SQLModel (Pydantic + SQLAlchemy) for ORM models
- JSON columns for flexible configuration
- Nested REST routes (`/products/{id}/templates`,
  `/users/{id}/deployments`)
- Service layer in `api/app/services/` shared by API and CLI

## Goals / Non-Goals

**Goals:**

- Introduce Plan and PlanTemplateVersion models that mirror the existing
  Product/ProductTemplateVersion pattern.
- Introduce a Subscription model that tracks a user's commitment to a
  specific plan template version.
- Ensure that every deployment is associated with a subscription (NOT NULL
  FK), so there is always a clear answer to "who is paying for this
  deployment and on what terms."
- Ensure that price changes to a plan do NOT affect existing subscriptions.
  This is a hard business requirement.
- Support free plans (price_cents = 0) with no payment provider redirect.
- Provide RESTful API endpoints for plans and subscriptions.
- Maintain API + CLI parity as required by project conventions.
- Backfill existing deployments with free-plan subscriptions in the
  migration so the NOT NULL constraint can be enforced immediately.

**Non-Goals:**

- Payment provider integration (Stripe, etc.) -- this change builds the
  data model and API; payment gateway integration is a separate change.
- UI changes for plan selection during deployment -- downstream dependency.
- Usage-based billing or metering -- out of scope.
- Plan bundling (one subscription covering multiple deployments) -- the
  data model supports this in the future via the N:1 relationship from
  deployment to subscription, but it is not implemented in this change.
- Proration, refunds, or billing cycle management.
- Trials or promotional pricing.

## Decisions

### 1. Mirror the Product/ProductTemplateVersion pattern for Plans

**Choice**: Create `PlanORM` (identity) and `PlanTemplateVersionORM`
(versioned commercial terms) as separate tables with the same canonical-
template-FK pattern used by Product.

**Rationale**: The Product/ProductTemplateVersion pattern is proven in this
codebase and solves the exact same versioning problem. A plan's commercial
terms (price, storage quota, billing interval) need to be immutable once
subscriptions reference them, but the plan's identity (name, which product
it belongs to) should be stable and mutable. This is precisely the
relationship between Product and ProductTemplateVersion.

The symmetry keeps cognitive overhead low -- developers already understand
this pattern from the product side:

```
Product  --1:N-->  ProductTemplateVersion   (what you deploy)
   |                        |
   | 1:N                    | via desired_template_id
   v                        v
 Plan    --1:N-->  PlanTemplateVersion      (what you pay)
                            |
                            | via plan_template_id
                            v
                      Subscription           (the billing record)
                            |
                            | via subscription_id
                            v
                       Deployment            (the running instance)
```

Product defines WHAT you can deploy. Plan defines HOW you can buy it. Both
version independently through template snapshots. Subscriptions lock in
commercial terms. Deployments lock in technical terms.

**Alternative considered**: A single `Plan` table with mutable price fields
and a status state machine (current/unlisted/discontinued). This was
rejected because mutating price fields would require either (a) accepting
that existing subscriptions see the new price (violates the core business
requirement) or (b) copying the plan's fields into the subscription at
creation time (data duplication, no single source of truth for what was
sold). The template-version approach avoids both problems.

**Alternative considered**: A status state machine on Plan
(current/unlisted/discontinued) to control plan visibility and lifecycle.
This was rejected because the template-version pattern already provides the
needed semantics: the "current" version of a plan is its canonical template,
and plan deletion is handled by soft delete. Adding a status field on top
of that would create two overlapping mechanisms for controlling plan
visibility. The Product model does not have a status field either -- it
uses soft delete for removal and the canonical template for versioning.
Plans should be consistent.

### 2. Subscription points to PlanTemplateVersion, not Plan

**Choice**: `SubscriptionORM.plan_template_id` is a FK to
`PlanTemplateVersionORM`, not to `PlanORM`.

**Rationale**: This is the mechanism that guarantees existing subscriptions
are not affected by price changes. When the admin creates a new plan
template version with a higher price and updates the plan's canonical
template, all existing subscriptions still point to the old template
version. The old template version is immutable and will not be deleted
(it is a permanent historical record). The subscription's commercial terms
are frozen at the moment of sale.

This is analogous to how `DeploymentORM.desired_template_id` points to
`ProductTemplateVersionORM`, not to `ProductORM`. The deployment knows
exactly which technical configuration it was created with, regardless of
whether the product's canonical template has since changed.

### 3. Deployment-to-Subscription is N:1 (FK on deployment)

**Choice**: `DeploymentORM.subscription_id` is a FK to `SubscriptionORM`.
Multiple deployments can point to the same subscription.

**Rationale**: While the current scope is effectively 1:1 (each deployment
gets its own subscription), the N:1 direction keeps the door open for
future bundle plans where a single subscription covers multiple
deployments. The FK on the deployment side means we can query "which
subscription pays for this deployment" with a simple join, and "which
deployments does this subscription cover" with a reverse lookup.

The FK is NOT NULL. Every deployment must have a billing context. This is
enforced at the database level to prevent orphaned deployments that have no
billing owner.

**Alternative considered**: Putting the FK on Subscription
(`subscription.deployment_id`) which would enforce 1:1. This was rejected
because it would require schema changes if we later need bundles, and it
would also require creating the deployment before the subscription (since
we would need the deployment ID for the FK), which conflicts with the
desired creation ordering (see Decision 5).

### 4. Free plans are signaled by price_cents = 0

**Choice**: A plan template version with `price_cents = 0` is a free plan.
The frontend checks this value to decide whether to show a payment flow.

**Rationale**: This is the simplest approach that meets current needs. There
are no current plans for trial tiers, $0-but-card-required plans, or other
scenarios where a zero price would be ambiguous. The YAGNI principle
applies: we should not add a `plan_type` enum or `is_free` boolean until
there is a concrete use case that `price_cents = 0` cannot express.

If the business later needs to distinguish between "truly free" and
"$0 but requires payment method on file" (e.g. for trials), a `plan_type`
enum on `PlanORM` (`free` / `paid`) would be a straightforward addition.

**Alternative considered**: An explicit `is_free` boolean on
PlanTemplateVersionORM. Rejected because it creates two sources of truth
(`price_cents` and `is_free`) that could contradict each other.

**Alternative considered**: A `plan_type` enum (`free` / `paid`) on PlanORM.
This is a clean design but adds a field with no current use case beyond
what `price_cents = 0` already provides. Deferred, not rejected.

### 5. Subscription is created atomically with deployment (server-side)

**Choice**: When a client calls `POST /users/{id}/deployments` with a
`plan_template_id` field, the server creates both a Subscription and a
Deployment in a single database transaction. The response is a standard
Deployment resource (which includes the new `subscription_id` FK).

**Rationale**: This avoids the orphan problem that arises with two separate
API calls:

```
PROBLEM: Two separate API calls

Client                              Server
  |                                   |
  |-- POST /subscriptions ----------->|  subscription created
  |<-- 201 {id: 42} -----------------|
  |                                   |
  |   [client crash / network error]  |
  |                                   |
  |-- POST /deployments ------------->|  never happens
  |       {subscription_id: 42}       |
  |                                   |
  Result: orphaned paid subscription  |
  with no deployment                  |


SOLUTION: Single atomic call

Client                              Server
  |                                   |
  |-- POST /users/3/deployments ----->|  BEGIN TRANSACTION
  |   { plan_template_id: 17,        |    Create Subscription
  |     desired_template_id: 5 }      |    Create Deployment
  |                                   |  COMMIT
  |<-- 201 {deployment} -------------|
  |   (includes subscription_id: 42)  |
  |                                   |
  Result: both exist or neither does  |
```

The response is a pure Deployment resource -- it does not return a composite
object. The `subscription_id` field on the deployment response is the
natural FK, not an ad-hoc addition. If the client needs subscription
details, it follows the reference: `GET /subscriptions/{id}`. This
preserves RESTfulness: each endpoint returns its own resource type.

The `plan_template_id` in the request body is an input parameter that
instructs the server how to create the deployment's billing context. It is
analogous to passing a `password` field when creating a user -- the field
drives server-side behavior but does not appear on the response resource.

**Alternative considered**: Separate `POST /subscriptions` and
`POST /deployments` endpoints with client-side orchestration. Rejected due
to the orphan problem described above. The two-call approach cannot
guarantee atomicity at the API boundary.

**Alternative considered**: Returning a composite response containing both
the deployment and subscription objects. Rejected because it violates REST
principles -- a deployment endpoint should return deployment resources. The
`subscription_id` FK on the deployment provides the link; the client can
follow it if needed.

### 6. Subscriptions are never soft-deleted

**Choice**: `SubscriptionORM` does not have a `deleted_at` column. Instead,
it has a `status` enum (`active` / `cancelled`) and a `cancelled_at`
timestamp.

**Rationale**: A subscription is a historical fact -- it represents a
commercial agreement that existed. Even after cancellation, the record is
needed for billing history, audit trails, analytics (e.g. average
subscription lifetime), and dispute resolution. There is no legitimate
reason to pretend a subscription never existed, which is what soft delete
semantics would imply.

The `status` field handles visibility:
- Active subscriptions: `WHERE status = 'active'`
- Billing history: all subscriptions for a user, regardless of status
- Is deployment paid for: `WHERE status = 'active' AND
  payment_status = 'current'`

### 7. Two orthogonal status axes on Subscription

**Choice**: Subscriptions have two separate status fields:
- `status` (lifecycle): `active` or `cancelled`
- `payment_status` (financial): `current` or `arrears`

**Rationale**: These are independent concerns that compose into a 2x2
matrix:

```
                     payment_status
                  current      arrears
              +------------+------------+
       active | Normal     | Past due   |
status        | operation  | grace      |
              |            | period     |
              +------------+------------+
    cancelled | Clean exit | Owes money |
              | no balance | after      |
              |            | cancel     |
              +------------+------------+
```

All four states are real and meaningful. Collapsing them into a single
status field would require states like `active_current`, `active_arrears`,
`cancelled_current`, `cancelled_arrears` -- which is just a less flexible
encoding of the same information.

Two columns also allows independent state transitions: a subscription can
go into arrears without being cancelled, and it can be cancelled while still
in arrears (the user still owes money). These transitions are orthogonal
and should not be coupled.

For v1, `active` and `cancelled` are sufficient lifecycle states. If the
business later needs `suspended` (service paused due to arrears but not
cancelled) or `pending` (payment not yet confirmed), adding enum values is
a trivial migration.

**Alternative considered**: A single `status` field with values like
`active`, `arrears`, `cancelled`. Rejected because `arrears` is a payment
state, not a lifecycle state. A subscription can be both active and in
arrears, or cancelled and in arrears. Conflating the two axes loses
information.

### 8. Monthly and annual billing intervals are separate Plans

**Choice**: If a product offers both monthly and annual billing, these are
modeled as two separate Plan records, not as two PlanTemplateVersions of
the same plan.

**Rationale**: Switching from monthly to annual billing is a plan change,
not a version upgrade. The billing interval fundamentally defines the plan's
identity -- "Monthly 1TB at $9.99/mo" and "Annual 1TB at $99/yr" are
different commercial offerings, not different versions of the same offering.

If they were modeled as versions, then updating the canonical template from
monthly to annual would imply that the "current" version of the plan is now
annual -- but existing monthly subscribers would still be on the old version.
This is technically correct but semantically confusing. Separate plans are
clearer.

The `billing_interval` field lives on `PlanTemplateVersionORM` (not PlanORM)
because it is part of the commercial terms that are frozen at subscription
time. However, in practice, all template versions of a given plan will have
the same billing interval.

### 9. Backfill strategy for existing deployments

**Choice**: The Alembic migration creates a visible free plan
(price_cents=0) per existing product, with an associated plan template
version and subscription for each existing deployment. The free plans are
NOT soft-deleted -- they remain visible so users can continue creating
deployments.

**Rationale**: Since `deployment.subscription_id` is NOT NULL, every
existing deployment must have a subscription. And since new deployments
require selecting a plan, there must be at least one visible plan per
product. Soft-deleting the backfill plans would leave users unable to
create new deployments until an admin manually creates real plans.

The migration steps:

```
1. CREATE TABLE plan
2. CREATE TABLE plan_template_version
3. CREATE TABLE subscription

4. For each existing Product:
   |-- Create PlanORM (name="Free", product_id=X)
   |-- Create PlanTemplateVersionORM (
   |       price_cents=0,
   |       billing_interval='monthly',
   |       storage_bytes=0,
   |       plan_id=above)
   +-- Set Plan.template_id -> above template

5. For each existing Deployment:
   +-- Create SubscriptionORM (
           plan_template_id = free template for that product,
           user_id = deployment.user_id,
           status = 'active',
           payment_status = 'current',
           created_at = deployment.created_at)

6. ALTER TABLE deployment ADD COLUMN subscription_id (nullable)

7. UPDATE deployment SET subscription_id = matched subscription

8. ALTER TABLE deployment ALTER COLUMN subscription_id SET NOT NULL
```

This is a phased rollout:
1. Migration runs -- free plans exist, all deployments linked
2. Admin creates real paid plans for each product
3. Frontend plan-selection flow goes live (separate change)

## Risks / Trade-offs

- **Migration complexity** -- The data migration involves creating records
  across three new tables and backfilling a FK on an existing table. This
  requires careful ordering and should be tested against a copy of
  production data. Mitigation: Steps 6-8 use the standard
  nullable-then-backfill-then-not-null pattern. The migration should be
  wrapped in a transaction.

- **PlanTemplateVersion proliferation** -- Over time, plans may accumulate
  many template versions as prices change. Mitigation: This is the same
  trade-off as ProductTemplateVersion, which the codebase already accepts.
  Old versions are lightweight rows. A future admin UI could display
  version history.

- **Free plan as default** -- Every product starts with a free plan after
  migration. If the admin forgets to create paid plans, all new deployments
  will be free. Mitigation: This is the intended behavior for the initial
  rollout. Payment enforcement comes with the payment gateway integration.

- **No payment validation** -- This change does not integrate with a payment
  provider. The `payment_status` field exists but is not driven by real
  payment events. Mitigation: The field defaults to `current`, which is
  correct for free plans. Payment integration is a planned follow-up change.

- **Subscription lifecycle is minimal** -- Only `active` and `cancelled`
  states. Mitigation: Adding states is a trivial enum migration. The two-
  axis design (status + payment_status) already handles the most important
  nuance.

## Complete Data Model

```
+-------------+       +--------------+       +----------------------------+
| ProductORM  |--1:N->|   PlanORM    |--1:N->| PlanTemplateVersionORM     |
| (existing)  |       |              |       |                            |
| id          |       | id           |       | id                         |
| name        |       | product_id   |       | plan_id (FK)               |
| description |       | name         |       | price_cents                |
| template_id |       | description  |       | billing_interval           |
| created_at  |       | template_id  |<--ref-|  (monthly|annual)          |
| deleted_at  |       |  (canonical) |       | storage_bytes              |
+-------------+       | sort_order   |       | created_at                 |
                      | created_at   |       +----------------------------+
                      | deleted_at   |
                      +--------------+
                                                          |
                                                     1:N  | plan_template_id
                                                          v
                  +--------------+       +------------------------------+
                  |DeploymentORM |--N:1->|     SubscriptionORM          |
                  | (existing)   |       |                              |
                  |              |       | id                           |
                  | subscription_|       | plan_template_id (FK, NN)    |
                  |  id (FK, NN) |       | user_id (FK, NN)             |
                  |              |       | status (active|cancelled)    |
                  |              |       | payment_status               |
                  |              |       |  (current|arrears)           |
                  |              |       | created_at                   |
                  |              |       | cancelled_at (nullable)      |
                  |              |       | external_ref (nullable)      |
                  |              |       | created_at                   |
                  |              |       |                              |
                  |              |       | (no deleted_at)              |
                  +--------------+       +------------------------------+
```

## API Design

All endpoints follow the existing nested-route conventions. Every endpoint
returns only its own resource type (pure REST -- no composite responses).

### Plan Browsing (public)

```
GET /products/{product_id}/plans        List visible plans for a product
GET /plans/{id}                         Get a single plan with its
                                          canonical template details
```

### Plan Administration (admin only)

```
POST   /products/{product_id}/plans     Create a new plan for a product
PUT    /plans/{id}                      Update plan name or canonical
                                          template_id
DELETE /plans/{id}                       Soft-delete a plan
POST   /plans/{plan_id}/templates       Create a new plan template version
```

### Subscription Management

```
GET    /users/{user_id}/subscriptions   List subscriptions for a user
GET    /subscriptions/{id}              Get a single subscription
PUT    /subscriptions/{id}              Update status (cancel) or
                                          payment_status
```

### Deployment Creation (modified)

```
POST   /users/{user_id}/deployments     Creates deployment AND subscription
                                          atomically. Request includes
                                          plan_template_id. Response is a
                                          Deployment resource with
                                          subscription_id.
```

The atomic creation flow:

```
Client                                     Server
  |                                          |
  |  POST /users/3/deployments               |
  |  { plan_template_id: 17,                |
  |    desired_template_id: 5,               |
  |    user_values_json: {} }                |
  |----------------------------------------->|
  |                                          |  BEGIN TRANSACTION
  |                                          |    Validate plan_template 17
  |                                          |    Create Subscription(
  |                                          |      plan_tmpl_id=17,
  |                                          |      user_id=3,
  |                                          |      status=active,
  |                                          |      payment_status=current)
  |                                          |    Create Deployment(
  |                                          |      subscription_id=above,
  |                                          |      desired_template_id=5,
  |                                          |      user_id=3)
  |                                          |  COMMIT
  |                                          |
  |<-----------------------------------------|
  |  201 Created                             |
  |  { "id": 88,                             |
  |    "subscription_id": 42,                |
  |    "desired_template_id": 5,             |
  |    "user_id": 3,                         |
  |    "status": "pending",                  |
  |    ... }                                 |
  |                                          |
  |  GET /subscriptions/42  (if needed)      |
  |----------------------------------------->|
  |<-----------------------------------------|
  |  200 OK                                  |
  |  { "id": 42,                             |
  |    "plan_template_id": 17,               |
  |    "status": "active",                   |
  |    "payment_status": "current",          |
  |    ... }                                 |
```

## Open Questions

- **Cancellation cascading**: When a deployment is deleted, should its
  subscription be automatically cancelled? For v1 with 1:1 semantics this
  seems correct, but it complicates the future bundle scenario. To be
  decided during implementation.
- **Grace period**: When a subscription enters arrears, how long before
  service is suspended or cancelled? This is a business policy question
  that affects the billing workflow, not the data model.
- **Plan ordering on the pricing page**: `sort_order` lives on PlanORM
  so it is stable across template version changes.
