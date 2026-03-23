## Why

Caelus has plans, subscriptions, and billing intervals, but no actual payment collection. Deployments on paid plans are created with `payment_status=current` unconditionally — everything is effectively free. We need to integrate an external payment provider to collect recurring subscription payments before provisioning paid deployments.

Mollie has been selected as the payment provider. The `mollie-api-py` SDK is already installed. Mollie supports recurring billing via a customer → first payment → mandate → subscription chain, which maps well to our existing subscription model.

## What Changes

- Users creating deployments on paid plans are redirected to Mollie's hosted checkout to complete an initial payment that establishes a recurring billing mandate
- Deployments on paid plans start in a new `pending` state and are only provisioned after the first payment succeeds via webhook confirmation
- A new unauthenticated webhook endpoint receives payment status updates from Mollie
- Recurring subscription payments are created automatically by Mollie and tracked in our database as a full audit trail
- A new `MolliePaymentORM` table records every payment with a JSON payload column for the full Mollie response
- A `PaymentProvider` protocol abstracts Mollie behind an injectable interface, with a `FakePaymentProvider` for CI testing
- Free plans (`price_cents=0`) bypass payment entirely — existing behavior is completely unchanged
- Currency is EUR-only; no multi-currency support needed

## Capabilities

### New Capabilities
- `mollie-payment-provider`: Payment provider abstraction (Protocol), real Mollie SDK wrapper, fake implementation for tests, configuration settings (API key, redirect URL, webhook base URL)
- `mollie-payment-data-model`: New MolliePaymentORM table for payment audit trail, mollie_customer_id on UserORM, Mollie payment status enum (open/pending/authorized/paid/canceled/expired/failed)
- `mollie-webhook`: Webhook endpoint for Mollie payment notifications, first-payment and recurring-payment handling, idempotent state transitions, reconciler triggering on payment confirmation
- `deployment-payment-states`: New `pending` deployment state for paid plans awaiting first payment, complete deployment state machine with all transitions

### Modified Capabilities
- `subscription-data-model`: Add `mollie_subscription_id` and `mollie_mandate_id` columns; drop `external_ref`; extend `payment_status` enum with `pending` value
- `deployment-create-contract`: Deployment creation response wrapped in envelope with `checkout_url` for paid plans; `pending` as initial status for paid deployments
- `deployment-subscription-integration`: Creation flow diverges for paid vs free — Mollie API call before DB transaction for paid plans; MolliePaymentORM record created atomically with subscription and deployment

## Impact

- **Backend**: New service module (`app/services/mollie.py`), new webhook route (`app/api/webhooks.py`), modified deployment creation service, new Alembic migration
- **Frontend**: DeployDialog redirects to Mollie checkout for paid plans; dashboard shows pending/arrears visual indicators on deployment cards
- **Dependencies**: `mollie-api-py` already installed; `httpx` upper bound already widened to `>=0.27`
- **Configuration**: New `CAELUS_MOLLIE_API_KEY`, `CAELUS_MOLLIE_REDIRECT_URL`, `CAELUS_MOLLIE_WEBHOOK_BASE_URL` settings; when API key is absent, all plans treated as free
- **Testing**: `FakePaymentProvider` enables full CI test coverage without Mollie connectivity; injectable via FastAPI dependency override
- **Database**: One new table (`mollie_payment`), two new columns on `subscription`, one new column on `user`, one dropped column on `subscription`, one extended enum; single Alembic migration
- **API parity**: CLI `deploy create` for paid plans is not supported (no browser for checkout redirect); CLI creates free deployments only, or requires `--skip-payment` admin flag
