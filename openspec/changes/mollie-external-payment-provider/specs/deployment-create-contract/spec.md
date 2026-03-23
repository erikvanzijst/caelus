## ADDED Requirements

### Requirement: Deployment creation response includes checkout URL for paid plans

The `POST /users/{user_id}/deployments` endpoint SHALL return an envelope response
containing both the deployment resource and an optional checkout URL:

```json
{
  "deployment": { "id": 88, "status": "pending", "subscription_id": 42, ... },
  "checkout_url": "https://payments.mollie.com/checkout/..."
}
```

For free plans (`price_cents = 0`) or when no payment provider is configured,
`checkout_url` SHALL be `null` and the `deployment.status` SHALL be `"provisioning"`
(existing behavior).

For paid plans with a payment provider configured, `checkout_url` SHALL contain the
Mollie hosted checkout URL and `deployment.status` SHALL be `"pending"`.

This envelope response applies ONLY to the creation endpoint. All other deployment
endpoints (`GET`, `PUT`, `DELETE`) SHALL continue to return the bare deployment
resource unchanged.

#### Scenario: Paid deployment creation returns checkout URL
- **WHEN** `POST /users/{user_id}/deployments` is called with a paid plan template
- **AND** a payment provider is configured
- **THEN** the response is 201 with body:
  - `deployment`: the deployment resource with `status = "pending"`
  - `checkout_url`: a Mollie checkout URL string

#### Scenario: Free deployment creation returns null checkout URL
- **WHEN** `POST /users/{user_id}/deployments` is called with a free plan template
- **THEN** the response is 201 with body:
  - `deployment`: the deployment resource with `status = "provisioning"`
  - `checkout_url`: `null`

#### Scenario: No payment provider returns null checkout URL
- **GIVEN** `CAELUS_MOLLIE_API_KEY` is not configured
- **WHEN** `POST /users/{user_id}/deployments` is called with any plan template
- **THEN** the response is 201 with `checkout_url: null`
- **AND** the deployment is created as if the plan were free

#### Scenario: GET deployment returns bare resource (no envelope)
- **WHEN** `GET /users/{user_id}/deployments/{id}` is called
- **THEN** the response is the deployment resource directly (no `checkout_url` wrapper)

### Requirement: Frontend redirects to Mollie checkout for paid plans

When the deployment creation API response includes a non-null `checkout_url`, the
frontend SHALL redirect the user's browser to that URL using
`window.location.href = checkout_url`. This abandons the current SPA state.

After payment (or cancellation), Mollie redirects the user back to the configured
`CAELUS_MOLLIE_REDIRECT_URL` (the dashboard). The app reloads and shows the
deployment card in its current state.

#### Scenario: Frontend redirect on paid plan
- **GIVEN** the user clicks "Launch" on a paid plan
- **WHEN** the API response includes `checkout_url = "https://payments.mollie.com/..."`
- **THEN** the browser navigates to the checkout URL
- **AND** the DeployDialog does not close normally (browser leaves the page)

#### Scenario: Frontend closes dialog on free plan
- **GIVEN** the user clicks "Launch" on a free plan
- **WHEN** the API response includes `checkout_url = null`
- **THEN** the DeployDialog closes normally (existing behavior)
- **AND** the deployment card appears on the dashboard

### Requirement: CLI refuses paid plan deployment creation

The `deploy create` CLI command SHALL refuse to create deployments for paid plans
when a payment provider is configured, because the CLI cannot redirect a browser
for Mollie checkout.

Free plan deployments via CLI SHALL continue to work as before.

#### Scenario: CLI create with paid plan
- **GIVEN** a payment provider is configured
- **AND** the plan template has `price_cents > 0`
- **WHEN** `deploy create --plan-template-id <paid_id> --template-id <id>` is run
- **THEN** the CLI exits with an error message indicating that paid deployments
  must be created via the web dashboard

#### Scenario: CLI create with free plan
- **GIVEN** a plan template with `price_cents = 0`
- **WHEN** `deploy create --plan-template-id <free_id> --template-id <id>` is run
- **THEN** the deployment is created successfully (existing behavior)
