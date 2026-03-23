## 1. Database Schema & Migration

- [ ] 1.1 Add `MolliePaymentStatus` enum to `app/models/billing.py` (open, pending, authorized, paid, canceled, expired, failed)
- [ ] 1.2 Add `MolliePaymentORM` model to `app/models/billing.py` with all columns: id (UUID), subscription_id (FK), mollie_payment_id (unique str), status (enum), sequence_type (str), amount_cents (int), created_at (datetime), payload (JSON)
- [ ] 1.3 Add `mollie_customer_id` (nullable str) to `UserORM` in `app/models/core.py`
- [ ] 1.4 Add `mollie_subscription_id` (nullable str) and `mollie_mandate_id` (nullable str) to `SubscriptionORM` in `app/models/billing.py`
- [ ] 1.5 Remove `external_ref` from `SubscriptionORM` in `app/models/billing.py`
- [ ] 1.6 Add `pending` value to `PaymentStatus` enum in `app/models/billing.py`
- [ ] 1.7 Add `pending` to the deployment status values (string field in `DeploymentORM`)
- [ ] 1.8 Create Alembic migration: add columns, drop `external_ref`, create `mollie_payment` table, extend `payment_status` enum
- [ ] 1.9 Update `SubscriptionORM` relationships to include `mollie_payments` backref
- [ ] 1.10 Remove `external_ref` from subscription Pydantic response models and API routes

## 2. Configuration

- [ ] 2.1 Add `mollie_api_key`, `mollie_redirect_url`, `mollie_webhook_base_url` to `CaelusSettings` in `app/config.py` (all optional, default None)

## 3. Payment Provider Abstraction

- [ ] 3.1 Create `app/services/mollie.py` with `PaymentProvider` Protocol defining: `ensure_customer`, `create_first_payment`, `get_payment`, `create_subscription`, `cancel_subscription`
- [ ] 3.2 Define `FirstPaymentResult` and `PaymentInfo` dataclasses/models as return types
- [ ] 3.3 Implement `MolliePaymentProvider` class wrapping `mollie.ClientSDK` with all protocol methods
- [ ] 3.4 Implement euro cent-to-Mollie string formatting (`1000` → `Amount(currency="EUR", value="10.00")`)
- [ ] 3.5 Implement `FakePaymentProvider` with in-memory state, deterministic IDs, and `_next_payment_status` control
- [ ] 3.6 Add `get_payment_provider()` dependency function in `app/deps.py` that returns `MolliePaymentProvider` when API key is set, `None` otherwise

## 4. Deployment Creation Flow (Paid Plans)

- [ ] 4.1 Modify `create_deployment()` in `app/services/deployments.py` to accept optional `PaymentProvider` parameter
- [ ] 4.2 Add paid-plan detection: if `price_cents > 0` and payment provider is not None, enter paid flow
- [ ] 4.3 Implement Mollie customer creation: call `ensure_customer()`, update `user.mollie_customer_id`
- [ ] 4.4 Implement first payment creation: call `create_first_payment()` with plan amount, redirect URL, webhook URL, metadata containing caelus_subscription_id
- [ ] 4.5 For paid plans: create SubscriptionORM with `payment_status=pending`, DeploymentORM with `status=pending`, MolliePaymentORM with `status=open`, `sequence_type=first` — all in one transaction AFTER Mollie API calls succeed
- [ ] 4.6 For paid plans: do NOT enqueue a reconcile job (provisioning waits for payment)
- [ ] 4.7 Return `checkout_url` from the service method alongside the deployment
- [ ] 4.8 Verify free plan flow is completely unchanged: `payment_status=current`, `status=provisioning`, reconcile job enqueued, no Mollie calls

## 5. API Response Changes

- [ ] 5.1 Create `DeploymentCreateResponse` Pydantic model with `deployment` and `checkout_url` fields
- [ ] 5.2 Update `POST /users/{user_id}/deployments` route in `app/api/users.py` to return the envelope response
- [ ] 5.3 Ensure all other deployment endpoints (GET, PUT, DELETE, list) continue returning bare deployment resource

## 6. Webhook Endpoint

- [ ] 6.1 Create `app/api/webhooks.py` with `POST /api/webhooks/mollie` route
- [ ] 6.2 Parse `id` from `application/x-www-form-urlencoded` request body
- [ ] 6.3 Implement payment lookup: check MolliePaymentORM by `mollie_payment_id`, then metadata, then Mollie subscription ID
- [ ] 6.4 Implement first-payment-paid handler: update subscription `payment_status` → `current`, deployment `status` → `provisioning`, enqueue reconcile job, create Mollie subscription, store `mollie_subscription_id` and `mollie_mandate_id`
- [ ] 6.5 Implement first-payment-failed handler: update subscription `payment_status` → `arrears`
- [ ] 6.6 Implement recurring-payment handler: insert/update MolliePaymentORM, update `payment_status` based on status (paid → current, failed → arrears)
- [ ] 6.7 Implement idempotency: only enqueue reconcile on `pending → current` transition, only create Mollie subscription when `mollie_subscription_id` is NULL
- [ ] 6.8 Handle unknown payment IDs: log warning, return 200
- [ ] 6.9 Register webhook router in `app/main.py` (no auth middleware on this route)
- [ ] 6.10 Implement billing interval to Mollie interval mapping: `monthly` → `"1 month"`, `annual` → `"12 months"`
- [ ] 6.11 Implement start date calculation: current date + one interval (to avoid double-charging)

## 7. CLI Changes

- [ ] 7.1 Update `deploy create` CLI command to detect paid plans and refuse with a message directing to the web dashboard
- [ ] 7.2 Verify free plan CLI deployment creation is unchanged

## 8. Frontend Changes

- [ ] 8.1 Update `DeployDialog` to handle the new envelope response (`{ deployment, checkout_url }`)
- [ ] 8.2 Implement Mollie redirect: if `checkout_url` is non-null, perform `window.location.href = checkout_url`
- [ ] 8.3 Add "Waiting for payment" indicator on deployment cards with `status = "pending"`
- [ ] 8.4 Add payment warning indicator on deployment cards where subscription `payment_status = "arrears"`
- [ ] 8.5 Ensure free plan flow in DeployDialog is unchanged (dialog closes normally)

## 9. Reconciler Integration

- [ ] 9.1 Update reconciler to skip deployments with `status = "pending"` (no reconcile jobs should exist for them, but add a guard)

## 10. Tests

- [ ] 10.1 Add `FakePaymentProvider` fixture to `conftest.py` with FastAPI dependency override
- [ ] 10.2 Test: paid deployment creation returns checkout_url, creates subscription (pending), deployment (pending), MolliePaymentORM (open)
- [ ] 10.3 Test: free deployment creation is unchanged — payment_status=current, status=provisioning, checkout_url=null, no MolliePaymentORM
- [ ] 10.4 Test: paid deployment creation when payment provider is None — treated as free
- [ ] 10.5 Test: Mollie API failure during paid creation — returns error, no DB records
- [ ] 10.6 Test: webhook first payment paid — subscription current, deployment provisioning, reconcile job, Mollie subscription created
- [ ] 10.7 Test: webhook first payment failed — subscription arrears, deployment stays pending
- [ ] 10.8 Test: webhook first payment expired — subscription arrears, deployment stays pending
- [ ] 10.9 Test: webhook recurring payment paid — new MolliePaymentORM row, subscription stays current
- [ ] 10.10 Test: webhook recurring payment failed — new MolliePaymentORM row, subscription arrears
- [ ] 10.11 Test: webhook recurring payment paid recovers from arrears — subscription arrears → current
- [ ] 10.12 Test: webhook duplicate (idempotent) — no second reconcile job, no second Mollie subscription
- [ ] 10.13 Test: webhook unknown payment ID — returns 200, no side effects
- [ ] 10.14 Test: CLI refuses paid plan deployment creation
- [ ] 10.15 Test: CLI creates free plan deployment normally
- [ ] 10.16 Test: subscription API no longer returns external_ref field
