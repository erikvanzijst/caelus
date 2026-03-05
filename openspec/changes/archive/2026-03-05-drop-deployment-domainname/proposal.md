## Why

Deployment contract handling for `domainname` is currently inconsistent across REST API, CLI, backend persistence, and UI. We need a single contract where clients do not send `domainname` on create/update, while reads continue to expose the persisted value derived from template-backed user input.

## What Changes

- Remove `domainname` from REST API `POST /deployments` and `PUT /deployments` request contracts.
- Remove `domainname` from CLI create-deployment and update-deployment inputs to keep CLI/API parity.
- Keep `domainname` in `GET /deployment` response payloads.
- In create-deployment and update-deployment service logic, derive `DeploymentORM.domainname` from `user_values_json` by recursively searching the template schema for the first field whose `title` matches `domainname` case-insensitively; persist `null` when no such field exists.
- Remove the dedicated `Domain name` TextField from the UI Dashboard and ensure UI request payloads do not send `domainname`.
- Update API and CLI unit tests to cover new validation and derivation behavior.
- **BREAKING**: API and CLI clients that still send `domainname` to `POST /deployments` or `PUT /deployments` must stop sending that field.

## Capabilities

### New Capabilities
- `deployment-domainname-contract`: Defines deployment `domainname` behavior across REST API, CLI, service persistence, and UI.

### Modified Capabilities
- None.

## Impact

- API: create/update request schemas, validation behavior, create service logic for derived persistence, and response contract checks.
- CLI: create/update command options/arguments and shared validation with service-layer parity to REST API.
- UI: Dashboard deployment form components and request builders/types.
- Tests: API and CLI unit tests for request validation, derivation, and response behavior.
