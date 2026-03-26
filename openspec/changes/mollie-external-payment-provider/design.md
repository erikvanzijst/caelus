## Context

Caelus provisions user-owned webapp instances on Kubernetes. Users select a product,
choose a plan (with pricing defined in PlanTemplateVersion), configure Helm values,
and launch a deployment. The system already models plans, subscriptions, and billing
intervals — but currently sets `payment_status=current` unconditionally, making
everything effectively free.

We are integrating Mollie as the external payment provider. The `mollie-api-py` SDK
(v1.2.3, Speakeasy-generated, using httpx) is already installed. Mollie's recurring
billing model uses a chain of objects: Customer → First Payment → Mandate →
Subscription → auto-generated Payments.

Relevant Mollie behavior:
- First payments with `sequenceType=first` authorize the customer and create a mandate
- Mandates store payment credentials (card, IBAN, PayPal) for future charges
- Mollie Subscriptions auto-generate payments at a specified interval (e.g. "1 month")
- Webhooks POST `id=tr_xxxxx` (form-encoded) for every payment status change
- Webhooks must return HTTP 200 within 15 seconds; Mollie retries 10× over 26 hours
- Mollie does NOT retry failed subscription payments; the next charge is at the next interval
- Payment statuses: open, pending, authorized, paid, canceled, expired, failed
- Definitive (terminal) statuses: paid, canceled, expired, failed

Key Mollie documentation references:
- Payments API overview: https://docs.mollie.com/reference/payments-api
- Creating payments: https://docs.mollie.com/reference/create-payment
- Accepting payments guide: https://docs.mollie.com/docs/accepting-payments
- Payment status handling: https://docs.mollie.com/docs/handling-payment-status
- Recurring payments guide: https://docs.mollie.com/docs/recurring-payments
- Subscriptions API: https://docs.mollie.com/reference/create-subscription
- Customers API: https://docs.mollie.com/reference/create-customer
- Webhooks: https://docs.mollie.com/docs/webhooks
- mollie-api-py SDK: https://github.com/mollie/mollie-api-py

The existing codebase uses:
- SQLModel ORM with Alembic migrations
- FastAPI routes delegating to a services layer
- A reconciler worker that provisions Helm releases
- React + MUI frontend with a DeployDialog component

## Goals / Non-Goals

**Goals:**
- Collect recurring subscription payments via Mollie before provisioning paid deployments
- Maintain a full audit trail of every payment from Mollie
- Keep free plans (`price_cents=0`) working exactly as they do today
- Make the Mollie integration fully testable in CI without network access
- Leave the architecture open for future arrears enforcement and subscription reactivation

**Non-Goals:**
- Multi-currency support (EUR-only for the foreseeable future)
- One-off payments (all paid plans are recurring subscriptions)
- Prorated billing on plan changes (future work)
- Automatic retry of failed subscription payments (Mollie does not support this)
- Customer-facing payment history UI (admin audit trail only for now)
- CLI support for paid plan deployment creation (requires browser for checkout)

## Decisions

### Decision 1: Data Model — Mirror Mollie's Object Hierarchy

**Choice:** Add `mollie_customer_id` to UserORM, add `mollie_subscription_id` and
`mollie_mandate_id` to SubscriptionORM, create a new `MolliePaymentORM` table, and
drop the existing `external_ref` column.

**Rationale:** Mollie models recurring billing as Customer → Subscription → Payments.
We should mirror this to maintain a full audit trail and enable future features like
payment history display and arrears enforcement.

```
UserORM
  ├── mollie_customer_id ─── (Mollie Customer cst_xxxxx)
  │
  └──< SubscriptionORM
         ├── mollie_subscription_id ─── (Mollie Subscription sub_xxxxx)
         ├── mollie_mandate_id ─── (Mollie Mandate mdt_xxxxx)
         ├── payment_status:  pending → current ↔ arrears
         │
         ├──< DeploymentORM  (1:1 in practice, FK on deployment)
         │
         └──< MolliePaymentORM  (1:N — the payment history)
               ├── [0] sequence_type=first, status=paid     ← initial checkout
               ├── [1] sequence_type=recurring, status=paid  ← month 2
               ├── [2] sequence_type=recurring, status=paid  ← month 3
               └── [3] sequence_type=recurring, status=failed ← month 4 (arrears)
```

**Why `mollie_customer_id` on UserORM (not SubscriptionORM):** A Mollie Customer maps
1:1 to a Caelus user. A user with multiple subscriptions shares one Mollie customer.
Mandates belong to customers, not subscriptions. Storing the customer ID on the user
avoids redundancy across subscriptions.

**Why drop `external_ref`:** It was a generic placeholder for "some external reference."
Now that we know the external provider is Mollie, explicit typed columns
(`mollie_subscription_id`, `mollie_mandate_id`) are clearer and self-documenting.

**Why a `payload` JSON column on MolliePaymentORM:** Mollie payment objects contain
many fields (method, details, settlement info, card data, etc.). Rather than creating
columns for every field upfront, we store the full Mollie response as JSONB. PostgreSQL
allows querying into it with `payload->>'method'` if needed. Key query fields (`status`,
`sequence_type`, `amount_cents`, `subscription_id`) are real columns for indexing and
aggregation.

**Why no currency column:** EUR-only. If multi-currency is needed later, a column can
be backfilled trivially — all existing records are EUR.

**Alternatives considered:**
- Separate Mollie customer table → Rejected. Only property is ID; email already on UserORM.
- Separate Mollie subscription table → Rejected. 1:1 with our SubscriptionORM; piggybacking is simpler.
- Individual columns for all Mollie payment fields → Rejected. Too many columns, most rarely queried. JSON payload gives flexibility.
- Keep `external_ref` alongside new columns → Rejected. It would be confusing to have both a generic ref and typed Mollie fields.

### Decision 2: Deployment State Machine — Add `pending` State

**Choice:** Introduce a `pending` deployment status for paid plans awaiting first
payment. Free plans skip it entirely.

```
 PAID PLAN                 FREE PLAN (enters here)
    │                               │
    ▼                               ▼
┌─────────┐  payment paid   ┌──────────────┐ helm success  ┌───────┐
│ pending │────────────────→│ provisioning │──────────────→│ ready │
└─────────┘                 └──────────────┘←──────────────└───────┘
  │                             ▲ │    ▲         upgrade        │
  │                      retry  │ │    │                        │
  │                             │ │fail│                        │
  │                             │ ▼    │ upgrade                │
  │                           ┌────────┐                        │
  │                           │ error  │                        │
  │                           └────────┘                        │
  │                               │                             │
  │ delete                 delete │                      delete │
  │                               ▼                             │
  │                        ┌──────────┐                         │
  └───────────────────────→│ deleting │←────────────────────────┘
                           └──────────┘
                                 │
                                 │ helm delete ok
                                 ▼
                            ┌─────────┐
                            │ deleted │
                            └─────────┘
```

**State definitions:**

| State        | Meaning                          | Reconciler? | Infrastructure? |
|--------------|----------------------------------|-------------|-----------------|
| pending      | Awaiting first payment           | No          | No              |
| provisioning | Helm install/upgrade in progress | Yes         | Being created   |
| ready        | Running normally                 | Idle        | Yes             |
| error        | Last reconcile failed            | Will retry  | Partial/broken  |
| deleting     | Helm delete in progress          | Yes         | Being removed   |
| deleted      | Soft-deleted, gone               | No          | No              |

**State transitions:**

| From         | To           | Trigger                                                |
|--------------|--------------|--------------------------------------------------------|
| pending      | provisioning | First payment webhook → `paid`. Enqueue reconcile job. |
| pending      | deleting     | User cancels deployment before paying.                 |
| provisioning | ready        | Reconciler: Helm install succeeds.                     |
| provisioning | error        | Reconciler: Helm install fails.                        |
| ready        | provisioning | Template upgrade or plan change triggers reconcile.    |
| ready        | deleting     | User deletes deployment.                               |
| error        | provisioning | Reconcile retry.                                       |
| error        | deleting     | User deletes deployment.                               |
| deleting     | deleted      | Reconciler: Helm delete succeeds.                      |

**Billing state vs infrastructure state are intentionally decoupled:**

`payment_status` lives on the subscription, `status` lives on the deployment. These are
independent dimensions:

```
              payment_status
              pending    current    arrears
           ┌──────────┬──────────┬──────────┐
  pending  │ normal   │    -     │    -     │  (awaiting first payment)
           ├──────────┼──────────┼──────────┤
  provis.  │    -     │ normal   │    -     │  (just paid, spinning up)
  status   ├──────────┼──────────┼──────────┤
  ready    │    -     │ normal   │ grace    │  (running but billing lapsed)
           ├──────────┼──────────┼──────────┤
  error    │    -     │ broken   │ broken   │  (infra problem)
           └──────────┴──────────┴──────────┘
```

The `ready + arrears` cell is where future arrears enforcement would kick in.

**Rationale:** `provisioning` currently signals active Helm activity expected to
complete momentarily — the UI polls in this state. Using it for "awaiting payment"
would mislead users. A distinct `pending` state clearly communicates "nothing is
happening on the platform yet, we're waiting for payment."

**Why not add a `suspended` state for arrears?** Not needed. Future arrears enforcement
can inject `caelus.replicas=0` into system_values, causing the reconciler to scale pods
to zero via normal Helm upgrade. The deployment stays `ready` (Helm release exists and
is healthy, just idle). Data (PVCs) is preserved. On reactivation, remove the override
and reconcile again. This requires zero state machine changes.

### Decision 3: Transaction Ordering — Mollie API Call Before DB Commit

**Choice:** Call the Mollie API to create the first payment before committing the DB
transaction. If Mollie fails, we never touch the database. If the DB commit fails
after Mollie succeeds, the Mollie payment simply expires unused.

```
PAID PLAN DEPLOYMENT CREATION:

  Client                        Server                          Mollie
    |                             |                               |
    |  POST /deployments          |                               |
    |  { plan_template_id,        |                               |
    |    desired_template_id,     |                               |
    |    user_values_json }       |                               |
    |────────────────────────────>|                               |
    |                             |                               |
    |                             |  Validate inputs              |
    |                             |  Generate deployment UUID     |
    |                             |  Ensure Mollie customer       |
    |                             |  exists for this user         |
    |                             |──────────────────────────────>|
    |                             |  POST /v2/customers           |
    |                             |  (if mollie_customer_id null) |
    |                             |<──────────────────────────────|
    |                             |  cst_xxxxx                    |
    |                             |                               |
    |                             |  Create first payment         |
    |                             |──────────────────────────────>|
    |                             |  POST /v2/customers/cst/pay   |
    |                             |  { sequenceType: "first",     |
    |                             |    amount: {EUR, "10.00"},    |
    |                             |    redirectUrl:               |
    |                             |      dashboard?deployment=id, |
    |                             |    webhookUrl,                |
    |                             |    idempotencyKey: dep UUID } |
    |                             |<──────────────────────────────|
    |                             |  tr_xxxxx + checkout URL      |
    |                             |                               |
    |                             |  BEGIN TRANSACTION            |
    |                             |    Create SubscriptionORM     |
    |                             |      payment_status=pending   |
    |                             |    Create DeploymentORM       |
    |                             |      status=pending           |
    |                             |    Create MolliePaymentORM    |
    |                             |      status=open              |
    |                             |  COMMIT                       |
    |                             |                               |
    |<────────────────────────────|                               |
    |  201 { deployment: {...},   |                               |
    |        checkout_url: "..." }|                               |
    |                             |                               |
    |  Browser redirect ─────────────────────────────────────────>|
    |                             |                               |
    |                             |        ... user pays ...      |
    |                             |                               |
    |                             |  POST /api/webhooks/mollie    |
    |                             |  id=tr_xxxxx                  |
    |                             |<──────────────────────────────|
    |                             |                               |
    |                             |  GET /v2/payments/tr_xxxxx    |
    |                             |──────────────────────────────>|
    |                             |<──────────────────────────────|
    |                             |  status=paid, mandateId=mdt   |
    |                             |                               |
    |                             |  Update subscription:         |
    |                             |    payment_status → current   |
    |                             |  Update deployment:           |
    |                             |    status → provisioning      |
    |                             |  Enqueue reconcile job        |
    |                             |                               |
    |                             |  Create Mollie subscription   |
    |                             |──────────────────────────────>|
    |                             |  POST /v2/customers/cst/subs  |
    |                             |  { amount, interval,          |
    |                             |    startDate: +1 interval }   |
    |                             |<──────────────────────────────|
    |                             |  sub_xxxxx                    |
    |                             |                               |
    |                             |  Store mollie_subscription_id |
    |                             |  Store mollie_mandate_id      |
    |                             |                               |
    |<──────── redirect ──────────────────────────────────────────|
    |  (user lands on dashboard,  |                               |
    |   sees deployment card      |                               |
    |   in provisioning state)    |                               |
```

**Why Mollie before DB:** If we commit first and then Mollie fails, we're stuck with
a `pending` deployment that can't get a checkout URL. The user would need to retry or
we'd need cleanup logic. By calling Mollie first, a failure means a clean error
response with no database artifacts.

**What if DB commit fails after Mollie succeeds?** The Mollie payment has no matching
records in our database. It will expire on its own (15 min to 12 days depending on
payment method). No money is collected without a customer completing checkout. This is
the safer failure mode.

**Alternative considered:** DB commit first, then Mollie call. Would require rollback
or cleanup on Mollie failure. More complex and leaves orphaned records on transient
failures.

### Decision 4: Payment Provider Abstraction — Protocol-Based Dependency Injection

**Choice:** Define a `PaymentProvider` Protocol that abstracts all Mollie interactions.
Provide `MolliePaymentProvider` (real) and `FakePaymentProvider` (tests). Inject via
FastAPI dependency.

```python
class PaymentProvider(Protocol):
    def ensure_customer(self, email: str, name: str | None = None) -> str: ...
    def create_first_payment(self, ...) -> FirstPaymentResult: ...
    def get_payment(self, payment_id: str) -> PaymentInfo: ...
    def create_subscription(self, ...) -> str: ...
    def cancel_subscription(self, customer_id: str, subscription_id: str) -> None: ...
```

All methods are synchronous. The existing codebase uses synchronous DB access and
synchronous FastAPI route handlers throughout. The `mollie-api-py` SDK supports both
sync (`client.payments.create()`) and async (`client.payments.create_async()`) — we
use the sync variants to stay consistent with the rest of the codebase.

**Rationale:** Tests in CI run against SQLite with no network access. Mocking at the
service boundary (not at httpx level) means we test our actual business logic — state
transitions, idempotency, error handling — without coupling to Mollie's SDK internals.

The Protocol approach (structural subtyping) means `FakePaymentProvider` doesn't inherit
from anything. It just implements the same method signatures. This keeps the fake
independent and simple.

**When `CAELUS_MOLLIE_API_KEY` is absent:** `get_payment_provider()` returns `None`.
The deployment service treats all plans as free. This allows development environments
to run without Mollie configuration.

### Decision 5: API Response Format — Envelope Wrapper for Creation

**Choice:** The deployment creation endpoint returns a wrapper object containing both
the deployment and an optional `checkout_url`:

```json
{
  "deployment": { "id": 88, "status": "pending", "subscription_id": 42, ... },
  "checkout_url": "https://payments.mollie.com/checkout/..."
}
```

For free plans, `checkout_url` is `null`. The frontend checks: if `checkout_url` is
present, redirect the browser; otherwise, close the dialog as today.

**Rationale:** The checkout URL is a transient, one-time value that does not belong
on the Deployment resource. It's a side-effect of creation, not a property of the
deployment. An envelope keeps the Deployment resource clean while providing the URL
in a self-documenting way.

**Why not a field on Deployment?** It would pollute the domain model with a value
that's only meaningful for ~5 seconds after creation and only for paid plans.

**Why not a Location/Link header?** Frontend fetch clients would need special header
parsing. The envelope is simpler and explicit.

**Why not HATEOAS `_links`?** Would introduce a pattern the codebase doesn't use
anywhere else. Over-engineering for a single use case.

### Decision 6: Webhook Design — Unauthenticated with Callback Verification

**Choice:** `POST /api/webhooks/mollie` is unauthenticated (no `X-Auth-Request-Email`
header required). It receives `id=tr_xxxxx` as form data, then calls Mollie's API to
fetch the payment and verify its status. This is Mollie's recommended security model.

**Webhook handler flow:**

```
1. Parse id from form body
2. Look up MolliePaymentORM by mollie_payment_id
   ├── Found → known payment (first payment or previously seen recurring)
   │   └── Fetch payment from Mollie, update record
   └── Not found → new recurring payment
       ├── Fetch payment from Mollie
       ├── Extract subscription_id from payment response
       ├── Look up SubscriptionORM by mollie_subscription_id
       ├── If found → insert new MolliePaymentORM record
       └── If not found → log warning, return 200 (don't leak info)
3. Based on status transition:
   ├── First payment paid (pending → current):
   │   ├── Update subscription.payment_status = current
   │   ├── Update deployment.status = provisioning
   │   ├── Enqueue reconcile job
   │   ├── Create Mollie subscription (recurring billing)
   │   └── Store mollie_subscription_id and mollie_mandate_id
   ├── First payment failed/expired/canceled:
   │   └── Update subscription.payment_status = arrears
   ├── Recurring payment paid:
   │   └── Ensure subscription.payment_status = current
   └── Recurring payment failed:
       └── Update subscription.payment_status = arrears
4. Return 200 OK
```

**Idempotency:** The handler checks current state before mutating. The reconcile job
is only enqueued when the payment_status transitions from `pending` to `current` (not
when it's already `current`). Duplicate webhooks for the same payment update the
MolliePaymentORM status but don't trigger side effects.

**15-second timeout:** The webhook must respond within 15 seconds. All Mollie API calls
(get_payment, create_subscription) happen synchronously in this window. If any call
fails, we return non-200 so Mollie retries. The create_subscription call on first
payment success is the most latency-sensitive — if it fails, the retry will attempt it
again (idempotent: check if mollie_subscription_id already set).

**Why return 200 for unknown payment IDs?** Returning an error would tell an attacker
"this ID doesn't exist in your system." Always return 200 to avoid information leakage.

### Decision 7: Avoiding Double-Charging

The first payment charges the subscription price (e.g., €10.00). This IS the first
period's payment. The Mollie subscription's `startDate` is set to one interval in the
future to avoid charging again immediately:

- Monthly plan, signed up March 23 → first payment €10, subscription startDate April 23
- Annual plan, signed up March 23 → first payment €120, subscription startDate March 23, 2027

The `billing_interval` enum on PlanTemplateVersion maps to Mollie intervals:
- `monthly` → `"1 month"`
- `annual` → `"12 months"`

### Decision 8: Frontend Flow — Simple Browser Redirect

**Choice:** When the API returns a `checkout_url`, the frontend performs a full browser
redirect (`window.location.href = checkout_url`), abandoning the SPA state. After
payment, Mollie redirects to the dashboard URL. The app reloads fresh and shows the
new deployment card.

The redirect URL given to Mollie is constructed from `CAELUS_MOLLIE_REDIRECT_URL` with
a `deployment` query parameter containing the pre-generated deployment UUID:

```
{CAELUS_MOLLIE_REDIRECT_URL}?deployment={deployment_id}
```

This works because `DeploymentORM.id` is a UUID4 generated client-side before the
Mollie API call — not a database sequence. The deployment ID is known before any
external calls or database transactions begin. The same UUID also serves as the Mollie
idempotency key for `create_first_payment`, protecting against duplicate payments on
retry.

The `deployment` query parameter allows the frontend to highlight or open the relevant
deployment when the user returns from Mollie checkout, even before the webhook has
arrived and transitioned the deployment from `pending` to `provisioning`.

**Future consideration (out of scope):** Give the deployment dialog its own URL path
and use that as the Mollie redirect URL, so the user returns to the open dialog.

### Decision 9: CLI Parity

The CLI cannot redirect a browser for Mollie checkout. For paid plans, `deploy create`
via CLI will refuse and show a message directing the user to the web dashboard.

An admin `--skip-payment` flag may be added later for operational use (e.g., granting
complimentary access), but is not in initial scope.

### Decision 10: Testing Strategy

**Protocol-based abstraction** is the foundation. All tests use `FakePaymentProvider`:

```python
class FakePaymentProvider:
    """In-memory fake for testing. State controllable from test code."""

    def __init__(self):
        self.customers: dict[str, str] = {}
        self.payments: dict[str, FakePayment] = {}
        self.subscriptions: dict[str, FakeSubscription] = {}
        self._next_payment_status = "paid"  # tests control this

    def simulate_paid(self, payment_id: str):
        """Helper: simulate a successful payment for webhook tests."""
        self.payments[payment_id].status = "paid"
        self.payments[payment_id].mandate_id = "mdt_fake_xxx"
```

Injected via FastAPI dependency override in test fixtures:

```python
fake_provider = FakePaymentProvider()
app.dependency_overrides[get_payment_provider] = lambda: fake_provider
```

**Test categories:**

| Category                      | What's tested                                                                                   | Mollie calls  |
|-------------------------------|-------------------------------------------------------------------------------------------------|---------------|
| Deployment creation (free)    | Existing flow unchanged, no Mollie involvement                                                  | None          |
| Deployment creation (paid)    | Subscription + deployment created as pending, checkout_url returned                             | Fake          |
| Webhook: first payment paid   | payment_status → current, deployment → provisioning, reconcile job, Mollie subscription created | Fake          |
| Webhook: first payment failed | payment_status → arrears, deployment stays pending                                              | Fake          |
| Webhook: recurring paid       | New MolliePaymentORM row, payment_status stays current                                          | Fake          |
| Webhook: recurring failed     | New MolliePaymentORM row, payment_status → arrears                                              | Fake          |
| Webhook: duplicate            | Idempotent — no double reconcile jobs                                                           | Fake          |
| Webhook: unknown ID           | Returns 200, logs warning                                                                       | Fake          |
| Mollie down during creation   | Error returned, no DB records                                                                   | Fake (raises) |

All run in CI with SQLite TestClient. No Mollie connectivity required.

## Risks / Trade-offs

**[Risk] Webhook arrives before Mollie API call returns to frontend**
→ Mitigation: Not a problem. The DB records are committed before the API response is
  sent. The webhook handler can find the subscription and deployment. The frontend
  redirect just hasn't happened yet — when it does, the deployment may already be
  provisioning.

**[Risk] Mollie subscription creation fails in webhook handler**
→ Mitigation: Return non-200 so Mollie retries. On retry, check if
  `mollie_subscription_id` is already set (idempotent). If it's still null, attempt
  creation again.

**[Risk] Payment expires and user never returns**
→ Mitigation: Deployment sits in `pending` state with `payment_status=arrears`. No
  infrastructure is provisioned (no cost). Orphaned pending deployments can be
  cleaned up by a future background job or admin action.

**[Risk] 15-second webhook timeout**
→ Mitigation: The webhook handler does at most 2 Mollie API calls (get_payment +
  create_subscription). Each has built-in retry with 7.5s max elapsed time. If the
  combined time exceeds 15s, Mollie will retry the webhook. Idempotent handling
  ensures correctness.

**[Risk] Mandate becomes invalid (card expires, SEPA failures)**
→ Mitigation: Future reactivation flow. The subscription and deployment records are
  mutable. Create a new first payment, redirect user through checkout, update
  `mollie_mandate_id` and `mollie_subscription_id`. The deployment stays as-is.
  Payment history is append-only — old and new payments coexist.

**[Risk] SQLite in tests doesn't support JSONB**
→ Mitigation: Use SQLAlchemy's `JSON` type which maps to `JSONB` on PostgreSQL and
  plain `JSON` (text) on SQLite. Query behavior differs but we only query the column
  via Python in tests, not via SQL operators.

**[Trade-off] EUR-only**
→ Accepted. Simplifies the data model (no currency column on payments). Backfilling
  a currency column later is trivial — all existing records are EUR.

**[Trade-off] No CLI support for paid deployments**
→ Accepted. The CLI cannot redirect a browser. Paid deployment creation requires the
  web dashboard. The CLI continues to work for free plans and for all other operations
  (list, update, delete, etc.).

## Migration Plan

A single Alembic migration that:

1. Adds `mollie_customer_id` (nullable string) to `user` table
2. Adds `mollie_subscription_id` (nullable string) to `subscription` table
3. Adds `mollie_mandate_id` (nullable string) to `subscription` table
4. Drops `external_ref` from `subscription` table
5. Extends `payment_status` enum to include `pending` value
6. Adds `pending` to deployment `status` (stored as string, not enum — no migration needed for this)
7. Creates `mollie_payment` table with columns:
   - `id` UUID PK
   - `subscription_id` FK → subscription NOT NULL
   - `mollie_payment_id` string UNIQUE NOT NULL
   - `status` enum (open/pending/authorized/paid/canceled/expired/failed)
   - `sequence_type` string NOT NULL
   - `amount_cents` integer NOT NULL
   - `created_at` datetime NOT NULL
   - `payload` JSONB

No data backfill needed — existing subscriptions have `payment_status=current` and
existing deployments have `status` in {provisioning, ready, deleting, deleted, error}.
The new `pending` values only apply to newly created records.

**Rollback:** Drop the `mollie_payment` table, remove the new columns, re-add
`external_ref`. The `pending` enum value can be left (PostgreSQL doesn't support
removing enum values without recreation).

## Open Questions

1. **Orphaned pending deployment cleanup:** Should there be a TTL on `pending`
   deployments after which they're automatically deleted? If so, what duration?
   (Mollie payments expire between 15 min and 12 days depending on method.)

2. **Admin override for payment:** Should admins be able to create deployments on paid
   plans without requiring payment (e.g., for partners, demos)? If so, a
   `--skip-payment` flag on the CLI and admin API would be needed.

3. **Subscription cancellation cascade:** When a user deletes a deployment, should we
   automatically cancel the Mollie subscription? Likely yes, but confirmation needed.
