## 1. Backend: Relax template version check and add status guard

- [ ] 1.1 In `api/app/services/deployments.py` `update_deployment()`: change the template version check from `<=` to `<` (line 229)
- [ ] 1.2 In `api/app/services/deployments.py` `update_deployment()`: replace the Python-level status check with an atomic SQL UPDATE that includes `WHERE status = 'ready'`. If 0 rows are affected, raise an appropriate exception
- [ ] 1.3 In `api/app/api/users.py`: catch the status guard exception and return HTTP 409 Conflict with a descriptive message
- [ ] 1.4 Add/update tests in `api/tests/` for: same-version update succeeds, downgrade still rejected, update blocked when status is `provisioning`/`error`/`deleting`, race condition returns 409

## 2. Frontend: Add updateDeployment API endpoint

- [ ] 2.1 In `ui/src/api/endpoints.ts`: add `updateDeployment(userId: number, deploymentId: number, payload: { desired_template_id: number; user_values_json?: object })` that sends PUT to `/api/users/{userId}/deployments/{deploymentId}`

## 3. Frontend: HostnameField initial hostname bypass

- [ ] 3.1 In `ui/src/components/HostnameField.tsx`: add optional `initialHostname?: string` prop
- [ ] 3.2 In the `validate` callback: if `fqdn === initialHostname`, set validation to `{ status: 'valid' }` and return without calling the API
- [ ] 3.3 Update `ui/src/components/HostnameField.test.tsx`: add tests for initial hostname bypass (skip on match, validate on change, skip again on revert)

## 4. Frontend: Thread initialHostname through component tree

- [ ] 4.1 In `ui/src/components/UserValuesForm.tsx`: add optional `initialHostname?: string` prop to `UserValuesFormProps`, pass it to `HostnameField` as `initialHostname`
- [ ] 4.2 In `ui/src/components/DeployDialogContent.tsx`: add optional `initialHostname?: string` and `submitLabel?: string` props, pass `initialHostname` to `UserValuesForm`, use `submitLabel` (default `"Launch"`) for the submit button text

## 5. Frontend: DeployDialog edit mode

- [ ] 5.1 In `ui/src/components/DeployDialog.tsx`: add optional `deployment?: Deployment` prop to `DeployDialogProps`
- [ ] 5.2 Add an `updateMutation` using `useMutation` that calls `updateDeployment()` with the deployment's id and the same `desired_template_id`
- [ ] 5.3 In `handleLaunch`: if `deployment` prop is present, call the update mutation instead of the create mutation
- [ ] 5.4 Change the `valuesToSend` fallback from `canonicalTemplate?.default_values_json` to `{}` (applies to both create and edit modes)
- [ ] 5.5 Pass `deployment?.hostname` as `initialHostname` and `deployment ? "Update" : "Launch"` as `submitLabel` to `DeployDialogContent`
- [ ] 5.6 Handle 409 Conflict errors from the update mutation by displaying an appropriate form error
- [ ] 5.7 Update `ui/src/components/DeployDialog.test.tsx`: add tests for edit mode (pre-population, PUT call, Update button text, 409 error handling)

## 6. Frontend: Dashboard Edit button

- [ ] 6.1 In `ui/src/pages/Dashboard.tsx`: add state for tracking which deployment is being edited (`editDeployment`)
- [ ] 6.2 Add an Edit button to deployment card `CardActions`, visible only when `deployment.status === 'ready'`
- [ ] 6.3 Wire the Edit button to open `DeployDialog` with the deployment's product and the `deployment` prop
- [ ] 6.4 Render the edit-mode `DeployDialog` when `editDeployment` is set, with `onClose` clearing the state
