## MODIFIED Requirements

### Requirement: Subscription has independent lifecycle and payment status

The system SHALL track subscription state on two orthogonal axes:

1. `status` (lifecycle): `active` or `cancelled`
2. `payment_status` (financial): `pending`, `current`, or `arrears`

These two fields are independent. All six combinations are valid:

```
                      payment_status
                   pending    current    arrears
               +----------+----------+----------+
        active | Awaiting | Normal   | Past due |
status         | first    | operation| grace    |
               | payment  |          | period   |
               +----------+----------+----------+
     cancelled |    -     | Clean    | Owes     |
               | (not     | exit, no | money    |
               | expected)| balance  | after    |
               |          |          | cancel   |
               +----------+----------+----------+
```

The `pending` payment status is the initial state for subscriptions linked to paid
plans. It indicates that the first payment has not yet been completed via the external
payment provider. Free subscriptions skip `pending` and start at `current`.

#### Scenario: Active subscription in good standing
- **WHEN** a subscription is created for a free plan
- **THEN** `status` defaults to `active`
- **AND** `payment_status` defaults to `current`

#### Scenario: Paid subscription starts as pending
- **WHEN** a subscription is created for a paid plan (`price_cents > 0`)
- **AND** a payment provider is configured
- **THEN** `status` defaults to `active`
- **AND** `payment_status` defaults to `pending`

#### Scenario: Subscription enters arrears
- **GIVEN** an active subscription with `payment_status='current'`
- **WHEN** `payment_status` is updated to `arrears`
- **THEN** the subscription is `status='active'`, `payment_status='arrears'`
- **AND** the subscription is still active (service may continue during
  grace period)

#### Scenario: Pending subscription transitions to current on payment
- **GIVEN** an active subscription with `payment_status='pending'`
- **WHEN** the first payment succeeds
- **THEN** `payment_status` transitions to `current`

#### Scenario: Pending subscription transitions to arrears on payment failure
- **GIVEN** an active subscription with `payment_status='pending'`
- **WHEN** the first payment fails, expires, or is canceled
- **THEN** `payment_status` transitions to `arrears`

#### Scenario: Cancel a subscription in good standing
- **GIVEN** an active subscription with `payment_status='current'`
- **WHEN** the subscription is cancelled
- **THEN** `status='cancelled'`, `payment_status='current'`
- **AND** `cancelled_at` is set to the current UTC timestamp

#### Scenario: Cancel a subscription in arrears
- **GIVEN** an active subscription with `payment_status='arrears'`
- **WHEN** the subscription is cancelled
- **THEN** `status='cancelled'`, `payment_status='arrears'`
- **AND** the user still owes money despite cancellation

#### Scenario: Payment resolved after cancellation
- **GIVEN** a cancelled subscription with `payment_status='arrears'`
- **WHEN** the payment is resolved and `payment_status` is updated to `current`
- **THEN** `status='cancelled'`, `payment_status='current'`

## ADDED Requirements

### Requirement: Subscription has Mollie subscription and mandate references

The `subscription` table SHALL have two new nullable string columns:

- `mollie_subscription_id`: The Mollie recurring subscription identifier (e.g.
  `sub_xxxxx`). Set after the first payment succeeds and the Mollie subscription
  is created. NULL for free subscriptions.
- `mollie_mandate_id`: The Mollie mandate identifier (e.g. `mdt_xxxxx`) that
  authorizes recurring charges. Set after the first payment succeeds. NULL for free
  subscriptions.

These fields are mutable to support reactivation: if a mandate becomes invalid
(e.g., card expires), a new first payment creates a new mandate and Mollie
subscription, and these fields are updated accordingly.

#### Scenario: Free subscription has no Mollie references
- **GIVEN** a plan template version with `price_cents=0`
- **WHEN** a subscription is created for this template
- **THEN** `mollie_subscription_id` is NULL
- **AND** `mollie_mandate_id` is NULL

#### Scenario: Mollie references set after first payment success
- **GIVEN** a subscription with `mollie_subscription_id = NULL`
- **WHEN** the first payment succeeds and a Mollie subscription is created
- **THEN** `mollie_subscription_id` is set to the Mollie subscription ID
- **AND** `mollie_mandate_id` is set to the mandate ID from the payment

#### Scenario: Mollie references updated on reactivation
- **GIVEN** a subscription with existing `mollie_subscription_id` and `mollie_mandate_id`
- **AND** the mandate has become invalid
- **WHEN** a new first payment succeeds and a new Mollie subscription is created
- **THEN** `mollie_subscription_id` is updated to the new Mollie subscription ID
- **AND** `mollie_mandate_id` is updated to the new mandate ID

## REMOVED Requirements

### Requirement: Subscription has external payment reference

**Reason:** The generic `external_ref` column is replaced by typed, explicit columns
(`mollie_subscription_id`, `mollie_mandate_id`) now that the external payment provider
is known to be Mollie. Explicit columns are self-documenting and avoid ambiguity about
what the field contains at different points in the payment lifecycle.

**Migration:** The Alembic migration drops the `external_ref` column. No data
migration is needed — the column is currently NULL for all existing subscriptions
(no payment provider was integrated before this change).
