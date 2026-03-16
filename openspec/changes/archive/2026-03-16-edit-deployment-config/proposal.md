## Why

Users can deploy applications with config values (hostname, etc.) through the DeployDialog, but once a deployment is running, there is no way to change those values. The only option is to delete and re-deploy — losing the deployment's identity, potentially its data, and requiring the user to reconfigure from scratch. Users need an Edit button on their deployment card that reopens the same form they used at creation time, lets them modify values, and triggers a Helm upgrade on submit.

## What Changes

- **Backend**: Relax the `update_deployment()` template version check from `<=` to `<` so that same-version value-only edits are allowed. Add an atomic status guard (`WHERE status = 'ready'`) so updates can only happen when the deployment is idle — preventing races with the reconciler.
- **Frontend**: Add an `updateDeployment()` API endpoint call. Extend `DeployDialog` to accept an optional existing `Deployment` and operate in edit mode (pre-populated form, PUT on submit, "Update" button text). Add `initialHostname` prop to `HostnameField` to skip re-validation when the hostname hasn't changed. Add an Edit button to deployment cards (visible only when status is `ready`).
- **Cleanup**: Change the `valuesToSend` fallback in `DeployDialog` from `default_values_json` to `{}` — the reconciler's merge chain applies template defaults as a base layer regardless of what the client sends.

## Capabilities

### New Capabilities
- `edit-deployment-backend`: Backend changes to support same-version deployment updates with atomic status guarding
- `edit-deployment-frontend`: Frontend edit mode for DeployDialog, HostnameField initial value bypass, Dashboard Edit button, and updateDeployment API call

### Modified Capabilities
- `deploy-dialog-shared`: DeployDialogContent gains an `initialHostname` prop (threaded to HostnameField) and the action button text becomes configurable
- `hostname-field-ui`: HostnameField gains an `initialHostname` prop to skip validation when the value matches the original
- `deployment-create-contract`: The `PUT /deployments` endpoint now accepts the same `desired_template_id` (not just a newer one)

## Impact

- **Code**: `api/app/services/deployments.py`, `api/app/api/users.py`, `ui/src/components/DeployDialog.tsx`, `ui/src/components/DeployDialogContent.tsx`, `ui/src/components/UserValuesForm.tsx`, `ui/src/components/HostnameField.tsx`, `ui/src/pages/Dashboard.tsx`, `ui/src/api/endpoints.ts`, test files
- **APIs**: `PUT /api/users/{user_id}/deployments/{deployment_id}` now allows same-version updates and returns 409 when deployment is not in `ready` state
- **Dependencies**: None
- **Systems**: No migrations, no infrastructure changes
