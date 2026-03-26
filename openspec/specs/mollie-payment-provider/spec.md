# mollie-payment-provider Specification

## Purpose

Define the PaymentProvider protocol, real and fake implementations, FastAPI
dependency injection, and Mollie configuration settings.

## ADDED Requirements

### Requirement: PaymentProvider protocol defines the Mollie integration boundary

The system SHALL define a `PaymentProvider` Protocol in `app/services/mollie.py` that
abstracts all external payment provider interactions. All Mollie SDK calls MUST go
through this protocol — no other module SHALL import or call `mollie.ClientSDK` directly.

The protocol SHALL define these methods:
- `ensure_customer(email, name) -> customer_id` — idempotent; creates if needed
- `create_first_payment(customer_id, amount_cents, redirect_url, webhook_url, metadata) -> FirstPaymentResult` — returns payment_id and checkout_url
- `get_payment(payment_id) -> PaymentInfo` — fetches current status and details
- `create_subscription(customer_id, mandate_id, amount_cents, interval, start_date, description, webhook_url, metadata) -> subscription_id`
- `cancel_subscription(customer_id, subscription_id) -> None`

All methods SHALL be synchronous, consistent with the rest of the codebase. The
`mollie-api-py` SDK provides both sync and async variants; we use the sync methods
(e.g. `client.payments.create()`, not `client.payments.create()`).

#### Scenario: Protocol is importable and defines all methods
- **WHEN** `PaymentProvider` is imported from `app.services.mollie`
- **THEN** it defines `ensure_customer`, `create_first_payment`, `get_payment`, `create_subscription`, and `cancel_subscription` as synchronous methods

### Requirement: MolliePaymentProvider wraps the mollie-api-py SDK

The system SHALL provide a `MolliePaymentProvider` class that implements the
`PaymentProvider` protocol using the `mollie.ClientSDK` from the `mollie-api-py`
package.

The constructor SHALL accept an `api_key` string parameter and initialize a
`ClientSDK` with `Security(api_key=api_key)`.

#### Scenario: Create Mollie customer
- **WHEN** `ensure_customer(email="user@example.com", name="Test User")` is called
- **AND** no Mollie customer exists for that email
- **THEN** the provider calls `client.customers.create` with the email and name
- **AND** returns the Mollie customer ID (e.g. `cst_xxxxx`)

#### Scenario: Create first payment with correct sequence type
- **WHEN** `create_first_payment` is called with `customer_id="cst_xxx"`, `amount_cents=1000`
- **THEN** the provider calls `client.payments.create` with:
  - `sequence_type=SequenceType.FIRST`
  - `customer_id="cst_xxx"`
  - `amount=Amount(currency="EUR", value="10.00")`
  - the provided `redirect_url`, `webhook_url`, and `metadata`
- **AND** returns a `FirstPaymentResult` containing the `payment_id` and `checkout_url`

#### Scenario: Amount formatting from cents to Mollie string
- **WHEN** `create_first_payment` is called with `amount_cents=999`
- **THEN** the Mollie API receives `amount.value="9.99"` and `amount.currency="EUR"`

#### Scenario: Create recurring subscription with correct start date
- **WHEN** `create_subscription` is called with `interval="1 month"`
- **THEN** the provider calls `client.subscriptions.create` with:
  - the provided `amount`, `interval`, `start_date`, `description`
  - `webhook_url` and `metadata` as provided
  - `customer_id` and `mandate_id` as provided
- **AND** returns the Mollie subscription ID (e.g. `sub_xxxxx`)

#### Scenario: Get payment returns status and metadata
- **WHEN** `get_payment(payment_id="tr_xxx")` is called
- **THEN** the provider calls `client.payments.get`
- **AND** returns a `PaymentInfo` object with `status`, `metadata`, `mandate_id`, `subscription_id`, and the raw response payload as a dict

### Requirement: FakePaymentProvider for testing

The system SHALL provide a `FakePaymentProvider` class that implements the
`PaymentProvider` protocol with in-memory state. Test code SHALL be able to control
the fake's behavior to simulate different payment outcomes.

The fake SHALL:
- Track customers, payments, and subscriptions in dictionaries
- Generate fake IDs with recognizable prefixes (e.g. `cst_fake_`, `tr_fake_`, `sub_fake_`)
- Allow tests to set `_next_payment_status` to control what `get_payment` returns
- Provide a `simulate_paid(payment_id)` helper for webhook testing

#### Scenario: Fake creates customer deterministically
- **WHEN** `ensure_customer(email="user@example.com")` is called on the fake
- **THEN** a customer ID starting with `cst_fake_` is returned
- **AND** calling it again with the same email returns the same customer ID

#### Scenario: Fake payment creation returns controllable checkout URL
- **WHEN** `create_first_payment(...)` is called on the fake
- **THEN** a `FirstPaymentResult` is returned with a `payment_id` starting with `tr_fake_`
- **AND** a `checkout_url` containing the payment ID

#### Scenario: Test controls payment status for webhook simulation
- **GIVEN** a fake payment was created with `create_first_payment`
- **WHEN** `fake._next_payment_status` is set to `"failed"`
- **AND** `get_payment(payment_id)` is called
- **THEN** the returned `PaymentInfo` has `status="failed"`

### Requirement: Payment provider injected via FastAPI dependency

The system SHALL provide a `get_payment_provider()` dependency function that returns:
- A `MolliePaymentProvider` instance when `CAELUS_MOLLIE_API_KEY` is configured
- `None` when `CAELUS_MOLLIE_API_KEY` is absent

The deployment service SHALL check if the payment provider is `None`. When it is,
all plans are treated as free regardless of `price_cents`.

#### Scenario: Payment provider available when API key configured
- **GIVEN** `CAELUS_MOLLIE_API_KEY` is set to `"test_xxx"`
- **WHEN** `get_payment_provider()` is called
- **THEN** a `MolliePaymentProvider` instance is returned

#### Scenario: No payment provider when API key absent
- **GIVEN** `CAELUS_MOLLIE_API_KEY` is not set
- **WHEN** `get_payment_provider()` is called
- **THEN** `None` is returned

#### Scenario: All plans treated as free when provider is None
- **GIVEN** the payment provider is `None`
- **AND** a plan template has `price_cents=1000`
- **WHEN** a deployment is created with that plan template
- **THEN** the deployment is created with `payment_status=current` and `status=provisioning`
- **AND** no Mollie API calls are made

### Requirement: Mollie configuration settings

`CaelusSettings` SHALL include these new fields:
- `CAELUS_MOLLIE_API_KEY: str | None = None` — Mollie API key (test_ or live_ prefix)
- `CAELUS_MOLLIE_REDIRECT_URL: str | None = None` — URL to redirect users after payment (the dashboard)
- `CAELUS_MOLLIE_WEBHOOK_BASE_URL: str | None = None` — publicly reachable base URL for webhook callbacks

All three are optional and default to `None`.

#### Scenario: Settings loaded from environment
- **GIVEN** `CAELUS_MOLLIE_API_KEY=test_xxx` is set in the environment
- **WHEN** `CaelusSettings` is instantiated
- **THEN** `settings.mollie_api_key == "test_xxx"`

#### Scenario: Settings default to None
- **GIVEN** no Mollie environment variables are set
- **WHEN** `CaelusSettings` is instantiated
- **THEN** `settings.mollie_api_key is None`
- **AND** `settings.mollie_redirect_url is None`
- **AND** `settings.mollie_webhook_base_url is None`
