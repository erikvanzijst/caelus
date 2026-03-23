# deployment-subscription-integration Specification

## Purpose

Define how deployments are linked to subscriptions via a NOT NULL foreign
key, how the atomic deployment+subscription creation works, and how the
data migration backfills existing records.

## ADDED Requirements

### Requirement: Every deployment has a subscription

The `deployment` table SHALL have a `subscription_id` column that is a
foreign key to `subscription.id` with a NOT NULL constraint. This ensures
that every deployment in the system has a clear billing context -- there is
always an answer to "who is paying for this deployment and on what terms."

#### Scenario: Deployment has subscription_id
- **WHEN** the deployment table schema is inspected
- **THEN** a `subscription_id` column exists
- **AND** it is NOT NULL
- **AND** it has a foreign key constraint referencing `subscription.id`

#### Scenario: Cannot create deployment without subscription
- **WHEN** a deployment is inserted with `subscription_id=NULL`
- **THEN** the database rejects the insert with a NOT NULL violation

### Requirement: Multiple deployments may share a subscription

The relationship from deployment to subscription is N:1. Multiple
deployment records MAY reference the same subscription. This supports
future bundle plans where one subscription covers multiple deployments.

For v1, each deployment will have its own subscription (effectively 1:1),
but the schema supports the N:1 case.

#### Scenario: Two deployments share a subscription
- **GIVEN** a subscription with id 42
- **WHEN** two deployments are created with `subscription_id=42`
- **THEN** both deployments are persisted successfully
- **AND** querying subscription 42's deployments returns both

### Requirement: Atomic deployment and subscription creation

When `POST /users/{user_id}/deployments` is called with a
`plan_template_id` field, the server SHALL create both a Subscription and
a Deployment within a single database transaction. If either creation
fails, neither is persisted.

This atomicity requirement prevents orphaned subscriptions (paid
subscriptions with no deployment) which would occur if the client had to
make two separate API calls.

```
ATOMIC CREATION FLOW:

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
  |                                          |      status='active',
  |                                          |      payment_status='current',
  |                                          |      created_at=now())
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
```

The response is a pure Deployment resource. The `subscription_id` field
is a natural FK on the deployment -- not an ad-hoc composite response.
If the client needs subscription details, it follows the reference with
`GET /subscriptions/{id}`.

#### Scenario: Successful atomic creation
- **GIVEN** plan template version 17 exists and is not deleted
- **AND** product template version 5 exists
- **AND** user 3 exists
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 17, "desired_template_id": 5}`
- **THEN** a subscription is created for user 3 referencing template 17
- **AND** a deployment is created for user 3 with `subscription_id`
  referencing the new subscription
- **AND** the response is 201 with the deployment resource
- **AND** the deployment response includes `subscription_id`

#### Scenario: Rollback on deployment failure
- **GIVEN** plan template version 17 exists
- **AND** creating the deployment would fail (e.g. hostname conflict)
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 17, "desired_template_id": 5}`
- **THEN** the transaction is rolled back
- **AND** no subscription is created
- **AND** no deployment is created

#### Scenario: Invalid plan template
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 999, "desired_template_id": 5}`
- **THEN** the response is 400 (invalid plan_template_id)
- **AND** no subscription or deployment is created

#### Scenario: Missing plan template
- **WHEN** `POST /users/3/deployments` is called with
  `{"desired_template_id": 5}` (no plan_template_id)
- **THEN** the response is 422 (plan_template_id is required)

### Requirement: plan_template_id is a request-only field

The `plan_template_id` field appears in the deployment creation request
body but is NOT a field on the Deployment resource itself. It is an input
parameter that instructs the server to create a subscription with that
template. The deployment's link to its billing context is through
`subscription_id`, not through a direct plan template reference.

This is analogous to passing a `password` field when creating a user --
the field drives server-side behavior but does not appear on the response
resource.

#### Scenario: plan_template_id not in deployment response
- **WHEN** a deployment is created with `plan_template_id: 17`
- **THEN** the deployment response does NOT contain a `plan_template_id`
  field
- **AND** the deployment response DOES contain `subscription_id`

#### Scenario: plan_template_id not in deployment read
- **WHEN** `GET /deployments/{id}` is called
- **THEN** the response does NOT contain a `plan_template_id` field

### Requirement: Deployment read response includes subscription_id

The `DeploymentRead` response model SHALL include the `subscription_id`
field so that clients can follow the reference to retrieve subscription
details.

#### Scenario: Deployment response includes subscription_id
- **GIVEN** a deployment with subscription_id 42
- **WHEN** the deployment is retrieved via GET
- **THEN** the response includes `"subscription_id": 42`

### Requirement: CLI deploy create requires plan template

The `deploy create` CLI command SHALL require a `--plan-template-id`
option. If omitted, the command SHALL exit with an error.

#### Scenario: CLI deploy create with plan template
- **WHEN** `deploy create --user-id 3 --plan-template-id 17
  --template-id 5` is run
- **THEN** a deployment and subscription are created atomically
- **AND** the deployment output includes `subscription_id`

#### Scenario: CLI deploy create without plan template
- **WHEN** `deploy create --user-id 3 --template-id 5` is run
- **THEN** the CLI exits with an error indicating that
  `--plan-template-id` is required

### Requirement: Data migration backfills free subscriptions

The Alembic migration SHALL create free plans and subscriptions for all
existing data so that the NOT NULL constraint on
`deployment.subscription_id` can be enforced immediately. The backfill
plans SHALL remain visible (NOT soft-deleted) so users can continue
creating deployments.

```
MIGRATION STEPS:

1. CREATE TABLE plan
2. CREATE TABLE plan_template_version
3. CREATE TABLE subscription
4. For each existing Product:
   |-- INSERT plan (name='Free', product_id=X)
   |-- INSERT plan_template_version (
   |       price_cents=0,
   |       billing_interval='monthly',
   |       storage_bytes=0,
   |       plan_id=above)
   +-- UPDATE plan SET template_id = above template
5. For each existing Deployment:
   +-- INSERT subscription (
           plan_template_id = free template for deployment's product,
           user_id = deployment.user_id,
           status = 'active',
           payment_status = 'current',
           created_at = deployment.created_at)
6. ALTER TABLE deployment ADD COLUMN subscription_id (nullable)
7. UPDATE deployment SET subscription_id = matched subscription
8. ALTER TABLE deployment ALTER COLUMN subscription_id SET NOT NULL
9. ADD FOREIGN KEY constraint on deployment.subscription_id
```

#### Scenario: Every product gets a free plan
- **GIVEN** 3 products exist before migration
- **WHEN** the migration runs
- **THEN** 3 free plans are created (one per product)
- **AND** each plan has a template version with `price_cents=0`
- **AND** each plan has its canonical `template_id` set
- **AND** the plans are NOT soft-deleted (visible to users)

#### Scenario: Every deployment gets a subscription
- **GIVEN** 10 deployments exist before migration across 3 products
- **WHEN** the migration runs
- **THEN** 10 subscriptions are created
- **AND** each subscription references the free template for its
  deployment's product
- **AND** each subscription has `status='active'` and
  `payment_status='current'`
- **AND** each subscription's `created_at` matches its deployment's
  `created_at`

#### Scenario: All deployments have subscription_id after migration
- **WHEN** the migration completes
- **THEN** every deployment has a non-null `subscription_id`
- **AND** the NOT NULL constraint is enforced

#### Scenario: Users can still create deployments after migration
- **GIVEN** the migration has completed
- **AND** product 1 has a visible free plan
- **WHEN** a user creates a deployment for product 1
- **THEN** the deployment is created with a new subscription to the
  free plan
