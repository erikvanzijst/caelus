## ADDED Requirements

### Requirement: Deployment has a pending state for paid plans

The deployment `status` field SHALL support a new value: `pending`. This state
indicates that the deployment has been created in the database but no infrastructure
provisioning has started because the first payment has not yet been confirmed.

The complete set of deployment statuses is: `pending`, `provisioning`, `ready`,
`error`, `deleting`, `deleted`.

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

#### Scenario: Paid deployment starts in pending state
- **WHEN** a deployment is created for a paid plan (`price_cents > 0`)
- **AND** a payment provider is configured
- **THEN** the deployment's initial `status` is `"pending"`
- **AND** no reconcile job is enqueued

#### Scenario: Free deployment skips pending state
- **WHEN** a deployment is created for a free plan (`price_cents = 0`)
- **THEN** the deployment's initial `status` is `"provisioning"`
- **AND** a reconcile job is enqueued immediately

#### Scenario: Pending deployment transitions to provisioning on payment
- **GIVEN** a deployment with `status = "pending"`
- **WHEN** the first payment webhook confirms `status = "paid"`
- **THEN** `deployment.status` becomes `"provisioning"`
- **AND** a reconcile job is enqueued

#### Scenario: Pending deployment can be deleted
- **GIVEN** a deployment with `status = "pending"`
- **WHEN** the user deletes the deployment
- **THEN** `deployment.status` transitions to `"deleting"` then `"deleted"`
- **AND** no Helm delete is needed (no infrastructure was provisioned)

### Requirement: Reconciler skips pending deployments

The reconciler worker SHALL NOT process deployments with `status = "pending"`. Only
the webhook handler can transition a deployment out of `pending` state (by moving it
to `provisioning` and enqueuing a reconcile job).

#### Scenario: Reconciler ignores pending deployment
- **GIVEN** a deployment with `status = "pending"` exists
- **WHEN** the reconciler worker runs
- **THEN** it does not attempt to provision or reconcile the pending deployment

### Requirement: Deployment state transitions are validated

The deployment service SHALL enforce valid state transitions. Invalid transitions
SHALL be rejected.

Valid transitions:
- `pending → provisioning` (payment confirmed)
- `pending → deleting` (user cancels before paying)
- `provisioning → ready` (Helm success)
- `provisioning → error` (Helm failure)
- `ready → provisioning` (template upgrade or plan change)
- `ready → deleting` (user deletes)
- `error → provisioning` (reconcile retry)
- `error → deleting` (user deletes)
- `deleting → deleted` (Helm delete success)

#### Scenario: Invalid transition from pending to ready
- **GIVEN** a deployment with `status = "pending"`
- **WHEN** an attempt is made to set `status = "ready"` directly
- **THEN** the transition is rejected (must go through `provisioning` first)

#### Scenario: Valid transition from pending to deleting
- **GIVEN** a deployment with `status = "pending"`
- **WHEN** the user requests deletion
- **THEN** the status transitions to `"deleting"`

### Requirement: Frontend shows payment-related visual indicators

The frontend deployment card SHALL display visual indicators based on the deployment's
payment-related state:

- `status = "pending"`: Show a "Waiting for payment" indicator (distinct from the
  "provisioning" spinner)
- `payment_status = "arrears"` (on the subscription): Show a warning indicator on
  the deployment card

The dashboard SHALL include `payment_status` from the subscription in its display
logic. The deployment list endpoint already includes `subscription_id`; the frontend
can fetch subscription details as needed.

#### Scenario: Pending deployment card appearance
- **GIVEN** a deployment with `status = "pending"`
- **WHEN** the dashboard renders the deployment card
- **THEN** the card shows a "Waiting for payment" or equivalent indicator
- **AND** does NOT show the provisioning spinner

#### Scenario: Arrears indicator on deployment card
- **GIVEN** a deployment with `status = "ready"`
- **AND** its subscription has `payment_status = "arrears"`
- **WHEN** the dashboard renders the deployment card
- **THEN** the card shows a payment warning indicator
