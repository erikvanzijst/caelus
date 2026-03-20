# subscription-data-model Specification

## Purpose

Define the Subscription database model that tracks a user's commitment to a
specific PlanTemplateVersion, with independent lifecycle and payment status
axes and no soft delete.

## ADDED Requirements

### Requirement: Subscription references a PlanTemplateVersion

The system SHALL store subscriptions in a `subscription` table. Each
subscription SHALL reference a specific `PlanTemplateVersion` via a
`plan_template_id` foreign key (NOT NULL). The subscription records WHICH
commercial terms were sold, not just which plan -- this ensures price
changes do not retroactively affect existing subscribers.

#### Scenario: Create a subscription
- **GIVEN** a plan template version with id 5 exists (price_cents=999)
- **AND** a user with id 3 exists
- **WHEN** a subscription is created with `plan_template_id=5`, `user_id=3`
- **THEN** the subscription is persisted with those values
- **AND** querying the subscription's plan_template returns the version
  with price_cents=999

#### Scenario: Subscription survives plan template change
- **GIVEN** a subscription references plan template version 5 (price_cents=999)
- **AND** the plan's canonical template is updated to version 6 (price_cents=1499)
- **WHEN** the subscription is queried
- **THEN** the subscription still references template version 5
- **AND** the subscription's effective price is 999 cents

### Requirement: Subscription belongs to a user

Each subscription SHALL reference a user via a `user_id` foreign key
(NOT NULL). A user MAY have zero or more subscriptions.

#### Scenario: List subscriptions for a user
- **GIVEN** user 3 has two active subscriptions and one cancelled subscription
- **WHEN** all subscriptions for user 3 are queried
- **THEN** three subscriptions are returned

### Requirement: Subscription has independent lifecycle and payment status

The system SHALL track subscription state on two orthogonal axes:

1. `status` (lifecycle): `active` or `cancelled`
2. `payment_status` (financial): `current` or `arrears`

These two fields are independent. All four combinations are valid:

```
                      payment_status
                   current      arrears
               +------------+------------+
        active | Normal     | Past due   |
status         | operation  | grace      |
               |            | period     |
               +------------+------------+
     cancelled | Clean exit | Owes money |
               | no balance | after      |
               |            | cancel     |
               +------------+------------+
```

#### Scenario: Active subscription in good standing
- **WHEN** a subscription is created
- **THEN** `status` defaults to `active`
- **AND** `payment_status` defaults to `current`

#### Scenario: Subscription enters arrears
- **GIVEN** an active subscription with `payment_status='current'`
- **WHEN** `payment_status` is updated to `arrears`
- **THEN** the subscription is `status='active'`, `payment_status='arrears'`
- **AND** the subscription is still active (service may continue during
  grace period)

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

### Requirement: Subscription records cancellation timestamp

The system SHALL store a `cancelled_at` datetime field (nullable) that is
set when the subscription transitions to `cancelled` status. This field
is NULL for active subscriptions.

#### Scenario: Active subscription has no cancellation date
- **GIVEN** a subscription with `status='active'`
- **THEN** `cancelled_at` is NULL

#### Scenario: Cancelled subscription has cancellation date
- **WHEN** a subscription is cancelled
- **THEN** `cancelled_at` is set to the current UTC timestamp
- **AND** this timestamp is preserved for billing history and analytics

### Requirement: Subscription has external payment reference

The system SHALL store an `external_ref` string field (nullable) for
referencing the subscription in an external payment provider (e.g. a
Stripe subscription ID). This field is NULL for free-plan subscriptions
and populated when payment integration is implemented.

#### Scenario: Free plan subscription
- **GIVEN** a plan template version with `price_cents=0`
- **WHEN** a subscription is created for this template
- **THEN** `external_ref` is NULL
- **AND** `payment_status` is `current` (nothing to owe)

#### Scenario: Paid plan subscription with external reference
- **GIVEN** a plan template version with `price_cents=999`
- **WHEN** a subscription is created with `external_ref='sub_abc123'`
- **THEN** the external reference is persisted for payment reconciliation

### Requirement: Subscriptions are never soft-deleted

The `subscription` table SHALL NOT have a `deleted_at` column.
Subscriptions are permanent historical records. Even after cancellation, a
subscription record is needed for:

- Billing history display ("cancelled on March 15")
- Audit trails and dispute resolution
- Analytics (average subscription lifetime, churn rate)
- Regulatory compliance (proof of what was sold)

The `status` field handles visibility in application queries:

- Active dashboard: `WHERE status = 'active'`
- Billing history: all subscriptions for user, regardless of status
- Is deployment paid for: `WHERE status = 'active' AND payment_status = 'current'`

#### Scenario: Query active subscriptions only
- **GIVEN** a user has 5 subscriptions: 3 active, 2 cancelled
- **WHEN** active subscriptions are queried with `status='active'`
- **THEN** 3 subscriptions are returned

#### Scenario: Query billing history
- **GIVEN** a user has 5 subscriptions: 3 active, 2 cancelled
- **WHEN** all subscriptions are queried for the user
- **THEN** 5 subscriptions are returned (including cancelled ones)

#### Scenario: No soft delete column exists
- **WHEN** the subscription table schema is inspected
- **THEN** there is no `deleted_at` column

### Requirement: Subscription has a start date

Each subscription SHALL have a `start_date` datetime field (NOT NULL) that
records when the subscription period began. This is distinct from
`created_at` (which records when the database row was inserted) -- for
backfilled subscriptions, `start_date` matches the original deployment's
`created_at`.

#### Scenario: New subscription start date
- **WHEN** a subscription is created as part of a new deployment
- **THEN** `start_date` is set to the current UTC timestamp

#### Scenario: Backfilled subscription start date
- **GIVEN** a deployment was created on 2026-01-15
- **WHEN** the migration backfills a subscription for this deployment
- **THEN** `start_date` is set to 2026-01-15 (the deployment's created_at)

### Requirement: Free subscriptions have payment_status current

For subscriptions referencing a plan template version with `price_cents=0`,
the `payment_status` SHALL always be `current`. There is nothing to owe on
a free plan.

#### Scenario: Free subscription payment status
- **GIVEN** a plan template version with `price_cents=0`
- **WHEN** a subscription is created for this template
- **THEN** `payment_status` is `current`
- **AND** `payment_status` should not transition to `arrears` (enforced
  by business logic, not database constraint)
