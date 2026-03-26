## ADDED Requirements

### Requirement: Webhook endpoint receives Mollie payment notifications

The system SHALL expose a `POST /api/webhooks/mollie` endpoint that receives payment
status notifications from Mollie. This endpoint SHALL:

- Accept `application/x-www-form-urlencoded` POST requests
- Parse the `id` field from the form body (Mollie payment ID, e.g. `tr_xxxxx`)
- NOT require authentication (no `X-Auth-Request-Email` header)
- Always return HTTP 200 OK (even for unknown payment IDs)
- Complete within 15 seconds (Mollie's webhook timeout)

The endpoint SHALL NOT trust the webhook payload alone. It MUST fetch the payment
from the Mollie API via `payment_provider.get_payment(payment_id)` to verify the
actual payment status.

#### Scenario: Valid webhook for known first payment
- **GIVEN** a MolliePaymentORM record exists with `mollie_payment_id = "tr_abc123"`
- **WHEN** `POST /api/webhooks/mollie` is called with form body `id=tr_abc123`
- **THEN** the handler fetches the payment from Mollie API
- **AND** updates the MolliePaymentORM record's status and payload
- **AND** returns HTTP 200

#### Scenario: Webhook for unknown recurring payment
- **GIVEN** no MolliePaymentORM record exists for `tr_new789`
- **AND** the Mollie API returns a payment with `subscription_id = "sub_xxx"`
- **AND** a SubscriptionORM exists with `mollie_subscription_id = "sub_xxx"`
- **WHEN** `POST /api/webhooks/mollie` is called with `id=tr_new789`
- **THEN** a new MolliePaymentORM record is inserted for this payment
- **AND** returns HTTP 200

#### Scenario: Webhook for completely unknown payment
- **GIVEN** no matching records exist for `tr_unknown`
- **AND** the Mollie API returns a payment with no matching subscription
- **WHEN** `POST /api/webhooks/mollie` is called with `id=tr_unknown`
- **THEN** the handler logs a warning
- **AND** returns HTTP 200 (does not leak information to potential attackers)

#### Scenario: Webhook endpoint is unauthenticated
- **WHEN** `POST /api/webhooks/mollie` is called without any auth headers
- **THEN** the request is accepted and processed (not rejected with 401/403)

### Requirement: First payment success triggers deployment provisioning

When a webhook arrives for a first payment (`sequence_type = "first"`) and the Mollie
API reports `status = "paid"`, the handler SHALL:

1. Update the MolliePaymentORM record: `status = "paid"`, `payload` updated
2. Update the SubscriptionORM: `payment_status` from `pending` to `current`
3. Update the DeploymentORM: `status` from `pending` to `provisioning`
4. Enqueue a reconcile job for the deployment (reason: `create`)
5. Create a Mollie recurring subscription via `payment_provider.create_subscription()`:
   - Amount: the plan template's `price_cents` formatted as EUR
   - Interval: derived from `billing_interval` (`monthly` → `"1 month"`, `annual` → `"12 months"`)
   - Start date: current date + one interval (to avoid double-charging the first period)
   - Webhook URL: the same webhook endpoint URL
   - Metadata: `{"caelus_subscription_id": "<subscription_id>"}`
6. Store the Mollie subscription ID on `subscription.mollie_subscription_id`
7. Store the mandate ID from the payment on `subscription.mollie_mandate_id`

The reconcile job enqueue SHALL only happen when `payment_status` transitions from
`pending` to `current`. If `payment_status` is already `current` (duplicate webhook),
no reconcile job is enqueued.

#### Scenario: First payment paid triggers full provisioning chain
- **GIVEN** a subscription with `payment_status = "pending"`
- **AND** a deployment with `status = "pending"`
- **AND** a MolliePaymentORM with `sequence_type = "first"`, `status = "open"`
- **WHEN** a webhook arrives and the Mollie API reports `status = "paid"`
- **THEN** `subscription.payment_status` becomes `"current"`
- **AND** `deployment.status` becomes `"provisioning"`
- **AND** a reconcile job is enqueued for the deployment
- **AND** `subscription.mollie_subscription_id` is set to a Mollie subscription ID
- **AND** `subscription.mollie_mandate_id` is set to the payment's mandate ID

#### Scenario: Double-charging avoided via subscription start date
- **GIVEN** a monthly plan at €10/month
- **AND** the first payment was made on 2026-03-23
- **WHEN** the Mollie subscription is created
- **THEN** the subscription's `start_date` is `"2026-04-23"`
- **AND** the interval is `"1 month"`

#### Scenario: Annual plan start date
- **GIVEN** an annual plan at €120/year
- **AND** the first payment was made on 2026-03-23
- **WHEN** the Mollie subscription is created
- **THEN** the subscription's `start_date` is `"2027-03-23"`
- **AND** the interval is `"12 months"`

### Requirement: First payment failure updates subscription status

When a webhook arrives for a first payment and the Mollie API reports a terminal
failure status (`failed`, `expired`, or `canceled`), the handler SHALL:

1. Update the MolliePaymentORM record status and payload
2. Update the SubscriptionORM: `payment_status` to `arrears`
3. NOT enqueue a reconcile job
4. NOT change the deployment status (stays `pending`)

#### Scenario: First payment expired
- **GIVEN** a subscription with `payment_status = "pending"`
- **AND** a deployment with `status = "pending"`
- **WHEN** a webhook arrives and the Mollie API reports `status = "expired"`
- **THEN** `subscription.payment_status` becomes `"arrears"`
- **AND** `deployment.status` remains `"pending"`
- **AND** no reconcile job is enqueued

#### Scenario: First payment canceled
- **GIVEN** a subscription with `payment_status = "pending"`
- **WHEN** a webhook arrives and the Mollie API reports `status = "canceled"`
- **THEN** `subscription.payment_status` becomes `"arrears"`

#### Scenario: First payment failed
- **GIVEN** a subscription with `payment_status = "pending"`
- **WHEN** a webhook arrives and the Mollie API reports `status = "failed"`
- **THEN** `subscription.payment_status` becomes `"arrears"`

### Requirement: Recurring payment success keeps subscription current

When a webhook arrives for a recurring payment (auto-generated by Mollie subscription)
and the status is `paid`, the handler SHALL:

1. Insert or update the MolliePaymentORM record
2. Ensure `subscription.payment_status` is `current` (set it if it was `arrears` — this handles recovery from a previously failed payment)

#### Scenario: Recurring payment succeeds while subscription is current
- **GIVEN** a subscription with `payment_status = "current"`
- **WHEN** a webhook arrives for a new recurring payment with `status = "paid"`
- **THEN** a new MolliePaymentORM record is inserted with `status = "paid"`
- **AND** `subscription.payment_status` remains `"current"`

#### Scenario: Recurring payment succeeds after arrears (recovery)
- **GIVEN** a subscription with `payment_status = "arrears"`
- **WHEN** a webhook arrives for a recurring payment with `status = "paid"`
- **THEN** `subscription.payment_status` becomes `"current"`

### Requirement: Recurring payment failure puts subscription in arrears

When a webhook arrives for a recurring payment and the status is `failed`, `expired`,
or `canceled`, the handler SHALL:

1. Insert or update the MolliePaymentORM record
2. Update `subscription.payment_status` to `arrears`

#### Scenario: Recurring payment fails
- **GIVEN** a subscription with `payment_status = "current"`
- **WHEN** a webhook arrives for a recurring payment with `status = "failed"`
- **THEN** a new MolliePaymentORM record is inserted with `status = "failed"`
- **AND** `subscription.payment_status` becomes `"arrears"`

#### Scenario: Recurring payment failure does not affect deployment status
- **GIVEN** a deployment with `status = "ready"`
- **WHEN** a recurring payment webhook reports `status = "failed"`
- **THEN** `deployment.status` remains `"ready"`
- **AND** only `subscription.payment_status` changes to `"arrears"`

### Requirement: Webhook handler is idempotent

The webhook handler MUST be idempotent. Processing the same webhook multiple times
SHALL produce the same result as processing it once.

Specific idempotency rules:
- If a MolliePaymentORM record already has the reported status, no state changes occur
- The reconcile job for first-payment success is only enqueued on the `pending → current`
  transition of `payment_status`. If already `current`, no job is enqueued.
- The Mollie subscription creation is only attempted when `mollie_subscription_id` is NULL.
  If already set, the creation is skipped.

#### Scenario: Duplicate webhook for first payment success
- **GIVEN** a first payment webhook was already processed (subscription is `current`,
  deployment is `provisioning`, Mollie subscription exists)
- **WHEN** the same webhook arrives again
- **THEN** no second reconcile job is enqueued
- **AND** no second Mollie subscription is created
- **AND** HTTP 200 is returned

#### Scenario: Duplicate webhook for recurring payment
- **GIVEN** a recurring payment webhook was already processed
- **WHEN** the same webhook arrives again
- **THEN** the MolliePaymentORM status is unchanged
- **AND** no duplicate side effects occur
- **AND** HTTP 200 is returned

### Requirement: Webhook lookup chains

The webhook handler SHALL use two lookup strategies depending on the payment type:

1. **First payment lookup:** The Mollie payment's `metadata.caelus_subscription_id`
   provides a direct reference to the Caelus SubscriptionORM. This is used because
   at the time of the first payment, the Mollie subscription does not exist yet
   (it's created after the first payment succeeds).

2. **Recurring payment lookup:** The Mollie payment's `subscription_id` field
   (Mollie's subscription ID) is matched against `SubscriptionORM.mollie_subscription_id`.
   This works because the Mollie subscription has been created by the time recurring
   payments start.

In both cases, the handler first checks if a MolliePaymentORM record exists for the
payment ID. If it does, the subscription is found via the existing record's FK.

#### Scenario: Lookup via metadata for first payment
- **GIVEN** a first payment was created with `metadata = {"caelus_subscription_id": "42"}`
- **WHEN** the webhook arrives and no MolliePaymentORM exists for this payment
- **THEN** the handler extracts `caelus_subscription_id` from the payment metadata
- **AND** looks up SubscriptionORM with `id = 42`

#### Scenario: Lookup via Mollie subscription ID for recurring payment
- **GIVEN** a recurring payment was auto-generated by Mollie subscription `sub_xxx`
- **AND** SubscriptionORM has `mollie_subscription_id = "sub_xxx"`
- **WHEN** the webhook arrives and no MolliePaymentORM exists for this payment
- **THEN** the handler extracts `subscription_id` from the Mollie payment response
- **AND** looks up SubscriptionORM where `mollie_subscription_id = "sub_xxx"`

#### Scenario: Lookup via existing MolliePaymentORM record
- **GIVEN** a MolliePaymentORM record exists with `mollie_payment_id = "tr_abc"`
- **AND** it references `subscription_id = 42`
- **WHEN** the webhook arrives for `tr_abc`
- **THEN** the handler uses the existing record's `subscription_id` for lookup
- **AND** does not need metadata or Mollie subscription ID
