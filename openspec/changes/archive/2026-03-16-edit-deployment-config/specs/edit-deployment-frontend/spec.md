## Overview

```
+--------------------------------------------------------------+
|                      Dashboard                               |
|                                                              |
| +------------------+  +------------------+                   |
| |  Deploy Card     |  |  Deploy Card     |                   |
| |                  |  |                  |                   |
| |  Status: ready   |  |  Status: error   |                   |
| | [Open][Edit][Del]|  | [Open]      [Del]|                   |
| +------------------+  +------------------+                   |
|     |                      (no Edit button)                  |
|     | click Edit                                             |
|     v                                                        |
| +----------------------------------------------------------+ |
| | DeployDialog (edit mode)                                 | |
| | +------------------------------------------------------+ | |
| | | DeployDialogContent                                  | | |
| | | +--------------------------------------------------+ | | |
| | | | UserValuesForm                                   | | | |
| | | |   hostname: [my.app.example.com]  <-- pre-filled | | | |
| | | |   theme:    [dark]                <-- pre-filled | | | |
| | | +--------------------------------------------------+ | | |
| | +------------------------------------------------------+ | |
| | [Cancel]                                        [Update] | |
| +----------------------------------------------------------+ |
|     |                                                        |
|     | submit                                                 |
|     v                                                        |
| PUT /api/users/{id}/deployments/{id}                         |
|   { desired_template_id: (same), user_values_json: {...} }   |
+--------------------------------------------------------------+
```

```
HostnameField validation logic (with initialHostname):

  current FQDN == initialHostname  --> status: valid (skip API)
  current FQDN != initialHostname  --> GET /api/hostnames/{fqdn}
  current FQDN reverts back        --> status: valid (skip API)
```

```
valuesToSend fallback (create mode, simplified):

  BEFORE: userValues ?? default_values_json ?? undefined
  AFTER:  userValues ?? {}

  Reconciler merge chain makes this safe:
    deep_merge(default_values_json, {}) == default_values_json
```

## ADDED Requirements

### Requirement: Dashboard shows Edit button on deployment cards
The Dashboard MUST display an Edit button on each deployment card. The Edit button MUST only be visible when the deployment's status is `ready`. Clicking the Edit button MUST open the `DeployDialog` in edit mode for that deployment.

#### Scenario: Edit button visible on ready deployment
- **WHEN** a deployment's status is `ready`
- **THEN** the deployment card shows an Edit button alongside the existing Open and Delete buttons

#### Scenario: Edit button hidden during provisioning
- **WHEN** a deployment's status is `provisioning`
- **THEN** the Edit button is not rendered on the deployment card

#### Scenario: Edit button hidden during error
- **WHEN** a deployment's status is `error`
- **THEN** the Edit button is not rendered on the deployment card

#### Scenario: Edit button opens DeployDialog in edit mode
- **WHEN** the user clicks the Edit button on a deployment card
- **THEN** the `DeployDialog` opens with the deployment's product, current `user_values_json` pre-populated in the form, and submit wired to the update endpoint

### Requirement: DeployDialog supports edit mode
The `DeployDialog` component MUST accept an optional `deployment` prop. When `deployment` is provided, the dialog operates in edit mode:
1. The form is pre-populated with `deployment.user_values_json`
2. On submit, the dialog calls `PUT /api/users/{user_id}/deployments/{deployment_id}` instead of `POST /api/users/{user_id}/deployments`
3. The submit button text reads "Update" instead of "Launch"
4. The deployment's current `hostname` is passed as `initialHostname` to the hostname field

#### Scenario: Edit dialog pre-populates existing values
- **WHEN** the DeployDialog opens in edit mode for a deployment with `user_values_json: {"ingress": {"hostname": "my.app"}, "settings": {"theme": "dark"}}`
- **THEN** the form fields show `my.app` in the hostname field and `dark` in the theme field

#### Scenario: Edit dialog submits via PUT
- **WHEN** the user modifies values in edit mode and clicks Update
- **THEN** the dialog calls `PUT /api/users/{user_id}/deployments/{deployment_id}` with the deployment's current `desired_template_id` and the modified `user_values_json`

#### Scenario: Create dialog behavior unchanged
- **WHEN** the DeployDialog is opened without a `deployment` prop
- **THEN** it behaves identically to the current implementation (empty form, POST on submit, "Launch" button)

#### Scenario: Edit dialog handles 409 Conflict
- **WHEN** the update request returns HTTP 409 (deployment not in ready state)
- **THEN** the dialog displays an error message indicating the deployment cannot be updated in its current state

### Requirement: DeployDialog create mode sends empty object when no values entered
In create mode, when the user does not enter any custom values, the `DeployDialog` MUST send `{}` (empty object) as `user_values_json` instead of falling back to `default_values_json`. The reconciler's merge chain applies template defaults as the base layer regardless.

#### Scenario: Create with no user input sends empty values
- **WHEN** the user opens the deploy dialog and clicks Launch without entering any values
- **THEN** the request payload contains `user_values_json: {}` (not the template's `default_values_json`)

### Requirement: updateDeployment frontend API endpoint
The frontend API layer MUST provide an `updateDeployment(userId, deploymentId, payload)` function that sends a `PUT /api/users/{user_id}/deployments/{deployment_id}` request with the given payload.

#### Scenario: Update deployment API call
- **WHEN** `updateDeployment(1, 42, { desired_template_id: 5, user_values_json: {...} })` is called
- **THEN** a PUT request is sent to `/api/users/1/deployments/42` with the payload

## MODIFIED Requirements

### deploy-dialog-shared: DeployDialogContent props interface

#### Modified: DeployDialogContent accepts initialHostname and configurable button text
- The `DeployDialogContent` component MUST accept an optional `initialHostname` prop that is threaded through `UserValuesForm` to `HostnameField`
- The `DeployDialogContent` component MUST accept an optional `submitLabel` prop (default: `"Launch"`) to configure the submit button text

### hostname-field-ui: HostnameField skips validation for unchanged hostname

#### Added Scenario: Initial hostname skips API validation
- **WHEN** `HostnameField` receives an `initialHostname` prop and the current FQDN equals `initialHostname`
- **THEN** the component sets validation status to `valid` without calling `GET /api/hostnames/{fqdn}`

#### Added Scenario: Changed hostname triggers normal validation
- **WHEN** `HostnameField` receives an `initialHostname` prop and the current FQDN differs from `initialHostname`
- **THEN** the component calls `GET /api/hostnames/{fqdn}` with the normal debounce behavior

#### Added Scenario: Reverted hostname skips validation again
- **WHEN** the user changes the hostname away from `initialHostname` and then changes it back
- **THEN** the component sets validation status to `valid` without calling the API
