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

## Requirements from mollie-external-payment-provider

### Requirement: Atomic deployment and subscription creation (updated for Mollie)

When `POST /users/{user_id}/deployments` is called with a `plan_template_id` field,
the server SHALL create a Subscription, Deployment, and (for paid plans) a
MolliePayment record within a single database transaction. If any creation fails,
none is persisted.

For **paid plans** (`price_cents > 0` and payment provider configured), the server
SHALL call the Mollie API BEFORE committing the database transaction. The flow is:

```
PAID PLAN CREATION FLOW:

Client                                     Server
  |                                          |
  |  POST /users/3/deployments               |
  |  { plan_template_id: 17,                |
  |    desired_template_id: 5,               |
  |    user_values_json: {} }                |
  |----------------------------------------->|
  |                                          |
  |                                          |  Validate inputs
  |                                          |  Ensure Mollie customer exists
  |                                          |    (create if user has no
  |                                          |     mollie_customer_id)
  |                                          |  Call Mollie: create first payment
  |                                          |    sequenceType=first
  |                                          |    amount from plan template
  |                                          |    -> get payment_id + checkout_url
  |                                          |
  |                                          |  BEGIN TRANSACTION
  |                                          |    Create Subscription(
  |                                          |      plan_tmpl_id=17,
  |                                          |      user_id=3,
  |                                          |      status='active',
  |                                          |      payment_status='pending')
  |                                          |    Create Deployment(
  |                                          |      subscription_id=above,
  |                                          |      desired_template_id=5,
  |                                          |      user_id=3,
  |                                          |      status='pending')
  |                                          |    Create MolliePayment(
  |                                          |      subscription_id=above,
  |                                          |      mollie_payment_id=tr_xxx,
  |                                          |      status='open',
  |                                          |      sequence_type='first')
  |                                          |  COMMIT
  |                                          |    (NO reconcile job enqueued)
  |                                          |
  |<-----------------------------------------|
  |  201 Created                             |
  |  { "deployment": { "id": 88,             |
  |      "subscription_id": 42,              |
  |      "status": "pending", ... },         |
  |    "checkout_url": "https://mollie/..." } |
```

For **free plans** (`price_cents = 0` or no payment provider), the existing flow is
unchanged:

```
FREE PLAN CREATION FLOW:

Client                                     Server
  |                                          |
  |  POST /users/3/deployments               |
  |  { plan_template_id: 10,                |
  |    desired_template_id: 5,               |
  |    user_values_json: {} }                |
  |----------------------------------------->|
  |                                          |  BEGIN TRANSACTION
  |                                          |    Create Subscription(
  |                                          |      plan_tmpl_id=10,
  |                                          |      user_id=3,
  |                                          |      status='active',
  |                                          |      payment_status='current')
  |                                          |    Create Deployment(
  |                                          |      subscription_id=above,
  |                                          |      desired_template_id=5,
  |                                          |      user_id=3,
  |                                          |      status='provisioning')
  |                                          |    Enqueue reconcile job
  |                                          |  COMMIT
  |                                          |
  |<-----------------------------------------|
  |  201 Created                             |
  |  { "deployment": { "id": 88,             |
  |      "subscription_id": 42,              |
  |      "status": "provisioning", ... },    |
  |    "checkout_url": null }                |
```

#### Scenario: Successful paid deployment creation
- **GIVEN** plan template version 17 exists with `price_cents=1000`
- **AND** product template version 5 exists
- **AND** user 3 exists
- **AND** a payment provider is configured
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 17, "desired_template_id": 5}`
- **THEN** a subscription is created with `payment_status='pending'`
- **AND** a deployment is created with `status='pending'`
- **AND** a MolliePayment record is created with `status='open'`, `sequence_type='first'`
- **AND** no reconcile job is enqueued
- **AND** the response is 201 with `checkout_url` set to a Mollie URL

#### Scenario: Successful free deployment creation (unchanged)
- **GIVEN** plan template version 10 exists with `price_cents=0`
- **AND** product template version 5 exists
- **AND** user 3 exists
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 10, "desired_template_id": 5}`
- **THEN** a subscription is created with `payment_status='current'`
- **AND** a deployment is created with `status='provisioning'`
- **AND** a reconcile job is enqueued
- **AND** no MolliePayment record is created
- **AND** the response is 201 with `checkout_url = null`

#### Scenario: Rollback on deployment failure (paid plan)
- **GIVEN** creating the deployment would fail (e.g. hostname conflict)
- **WHEN** `POST /users/3/deployments` is called with a paid plan
- **THEN** the transaction is rolled back
- **AND** no subscription, deployment, or MolliePayment is created
- **AND** the Mollie payment created before the transaction will expire unused

#### Scenario: Mollie API failure prevents deployment creation
- **GIVEN** the Mollie API is unavailable
- **WHEN** `POST /users/3/deployments` is called with a paid plan
- **THEN** the API returns an error (502 or 503)
- **AND** no subscription or deployment is created
- **AND** no database records are persisted

#### Scenario: Rollback on deployment failure (free plan, unchanged)
- **GIVEN** plan template version 10 exists with `price_cents=0`
- **AND** creating the deployment would fail (e.g. hostname conflict)
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 10, "desired_template_id": 5}`
- **THEN** the transaction is rolled back
- **AND** no subscription is created
- **AND** no deployment is created

#### Scenario: Invalid plan template (unchanged)
- **WHEN** `POST /users/3/deployments` is called with
  `{"plan_template_id": 999, "desired_template_id": 5}`
- **THEN** the response is 400 (invalid plan_template_id)
- **AND** no subscription or deployment is created

#### Scenario: Missing plan template (unchanged)
- **WHEN** `POST /users/3/deployments` is called with
  `{"desired_template_id": 5}` (no plan_template_id)
- **THEN** the response is 422 (plan_template_id is required)

### Requirement: Deployment UUID pre-generated before Mollie calls

During paid deployment creation, the server SHALL generate the deployment UUID
(`uuid4()`) before making any Mollie API calls or database transactions. This
pre-generated UUID is used for:

1. **Redirect URL**: Appended as `?deployment={uuid}` to `CAELUS_MOLLIE_REDIRECT_URL`,
   so the frontend can identify and focus on the new deployment when the user returns
   from Mollie checkout.
2. **Idempotency key**: Passed as the `idempotency_key` to `create_first_payment`,
   ensuring that retried requests produce the same Mollie payment rather than duplicates.
3. **Primary key**: Used as `DeploymentORM.id` when the database record is created.

#### Scenario: Redirect URL includes deployment UUID
- **GIVEN** `CAELUS_MOLLIE_REDIRECT_URL` is `"https://app.example.com/dashboard"`
- **WHEN** a paid deployment is created with pre-generated UUID `abc-def-123`
- **THEN** the redirect URL sent to Mollie is
  `"https://app.example.com/dashboard?deployment=abc-def-123"`

#### Scenario: Deployment UUID used as idempotency key
- **WHEN** a paid deployment is created
- **THEN** `create_first_payment` is called with `idempotency_key` equal to the
  string representation of the deployment UUID

### Requirement: Mollie customer ensured before payment creation

During paid deployment creation, the server SHALL ensure the user has a Mollie
customer before creating the first payment. If `user.mollie_customer_id` is NULL,
the server SHALL call `payment_provider.ensure_customer()` and store the returned
customer ID on the UserORM record.

This happens BEFORE the database transaction, alongside the Mollie payment creation.

#### Scenario: First paid deployment creates Mollie customer
- **GIVEN** user 3 has `mollie_customer_id = NULL`
- **WHEN** user 3 creates a paid deployment
- **THEN** a Mollie customer is created with the user's email
- **AND** `user.mollie_customer_id` is updated to the Mollie customer ID

#### Scenario: Subsequent paid deployment reuses Mollie customer
- **GIVEN** user 3 has `mollie_customer_id = "cst_abc123"`
- **WHEN** user 3 creates another paid deployment
- **THEN** no new Mollie customer is created
- **AND** `cst_abc123` is used as the customer ID for the payment
