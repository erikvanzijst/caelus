## MODIFIED Requirements

### Requirement: Atomic deployment and subscription creation

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
  |                                          |    → get payment_id + checkout_url
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
