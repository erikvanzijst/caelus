# subscription-api Specification

## Purpose

Define the RESTful API endpoints and CLI commands for viewing and managing
subscriptions.

## ADDED Requirements

### Requirement: List subscriptions for a user

The system SHALL provide a `GET /users/{user_id}/subscriptions` endpoint
that returns all subscriptions for the given user, including both active
and cancelled subscriptions. This follows the existing nested-route
convention (`/users/{id}/deployments`). The response is a list of
Subscription resources, each including the referenced plan template
version details.

#### Scenario: List all subscriptions for a user
- **GIVEN** user 3 has 2 active and 1 cancelled subscription
- **WHEN** `GET /users/3/subscriptions` is called
- **THEN** the response contains 3 subscription objects
- **AND** each includes plan template version details (price, interval)

#### Scenario: User with no subscriptions
- **GIVEN** user 5 has no subscriptions
- **WHEN** `GET /users/5/subscriptions` is called
- **THEN** the response contains an empty list

#### Scenario: List subscriptions for nonexistent user
- **WHEN** `GET /users/999/subscriptions` is called
- **THEN** the response is 404

### Requirement: Get a single subscription

The system SHALL provide a `GET /subscriptions/{subscription_id}` endpoint
that returns a single subscription with its plan template version details.

#### Scenario: Get an existing subscription
- **GIVEN** subscription 42 exists for user 3
- **WHEN** `GET /subscriptions/42` is called
- **THEN** the response contains the subscription with plan template
  version details, status, payment_status, and cancelled_at

#### Scenario: Get a nonexistent subscription
- **WHEN** `GET /subscriptions/999` is called
- **THEN** the response is 404

### Requirement: Cancel a subscription

The system SHALL provide a `PUT /subscriptions/{subscription_id}`
endpoint that allows updating the subscription's `status` to `cancelled`.
When cancelled, `cancelled_at` SHALL be set to the current UTC timestamp.
Cancelling an already-cancelled subscription SHALL be idempotent (no
error, no change to `cancelled_at`).

#### Scenario: Cancel an active subscription
- **GIVEN** subscription 42 is active with `payment_status='current'`
- **WHEN** `PUT /subscriptions/42` is called with
  `{"status": "cancelled"}`
- **THEN** `status` is `cancelled`
- **AND** `cancelled_at` is set to the current UTC timestamp
- **AND** the response is 200 with the updated subscription

#### Scenario: Cancel an active subscription in arrears
- **GIVEN** subscription 42 is active with `payment_status='arrears'`
- **WHEN** `PUT /subscriptions/42` is called with
  `{"status": "cancelled"}`
- **THEN** `status` is `cancelled`
- **AND** `payment_status` remains `arrears`
- **AND** `cancelled_at` is set

#### Scenario: Cancel an already-cancelled subscription
- **GIVEN** subscription 42 is already cancelled with
  `cancelled_at='2026-03-15T10:00:00Z'`
- **WHEN** `PUT /subscriptions/42` is called with
  `{"status": "cancelled"}`
- **THEN** the response is 200
- **AND** `cancelled_at` is unchanged (still '2026-03-15T10:00:00Z')

#### Scenario: Reactivate a cancelled subscription
- **GIVEN** subscription 42 is cancelled
- **WHEN** `PUT /subscriptions/42` is called with
  `{"status": "active"}`
- **THEN** the response is 400 (reactivation is not supported in v1)

### Requirement: Update payment status

The system SHALL allow updating a subscription's `payment_status` via
`PUT /subscriptions/{subscription_id}`. Valid transitions:
`current` to `arrears` and `arrears` to `current`.

#### Scenario: Mark subscription as in arrears
- **GIVEN** subscription 42 is active with `payment_status='current'`
- **WHEN** `PUT /subscriptions/42` is called with
  `{"payment_status": "arrears"}`
- **THEN** `payment_status` is `arrears`
- **AND** `status` remains `active`

#### Scenario: Resolve arrears
- **GIVEN** subscription 42 has `payment_status='arrears'`
- **WHEN** `PUT /subscriptions/42` is called with
  `{"payment_status": "current"}`
- **THEN** `payment_status` is `current`

### Requirement: Subscription response format

The subscription response resource SHALL include the following fields:

- `id` -- subscription primary key
- `plan_template_id` -- FK to the plan template version
- `user_id` -- FK to the user
- `status` -- `active` or `cancelled`
- `payment_status` -- `current` or `arrears`
- `cancelled_at` -- when cancelled (null if active)
- `external_ref` -- external payment provider reference (null if free)
- `created_at` -- when the database record was created

The response MAY include nested plan template version details (price_cents,
billing_interval, storage_bytes, plan name) for convenience.

#### Scenario: Active subscription response
- **GIVEN** an active subscription to a $9.99/mo plan
- **WHEN** the subscription is queried
- **THEN** the response includes:
  - `status: "active"`
  - `payment_status: "current"`
  - `cancelled_at: null`
  - Plan template details showing `price_cents: 999`,
    `billing_interval: "monthly"`

#### Scenario: Cancelled subscription response
- **GIVEN** a cancelled subscription
- **WHEN** the subscription is queried
- **THEN** the response includes:
  - `status: "cancelled"`
  - `cancelled_at: "2026-03-15T10:00:00Z"`

### Requirement: CLI parity for subscription management

The CLI SHALL provide commands equivalent to subscription API endpoints:

- `subscription list <user_id>` -- list subscriptions for a user
- `subscription cancel <subscription_id>` -- cancel a subscription

#### Scenario: CLI list subscriptions
- **WHEN** `subscription list 3` is run
- **THEN** the output displays subscriptions for user 3 in YAML format

#### Scenario: CLI cancel subscription
- **WHEN** `subscription cancel 42` is run
- **THEN** the subscription is cancelled
- **AND** the updated subscription is displayed in YAML format
