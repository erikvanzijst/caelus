## 1. API and CLI Write Contract Update

- [x] 1.1 Remove `domainname` from REST API `POST /deployments` and `PUT /deployments` request models/schemas.
- [x] 1.2 Update CLI create-deployment and update-deployment inputs to remove/reject `domainname` and keep parity with API write contracts.
- [x] 1.3 Add/update API unit tests to assert `domainname` is rejected for both create and update requests.
- [x] 1.4 Add/update CLI unit tests to assert `domainname` is not accepted for create and update commands.

## 2. Service Domain Derivation Behavior

- [x] 2.1 In create-deployment and update-deployment service logic, load the jsonschema for `desired_template` and recursively search the entire schema for the first field whose `title` matches `domainname` case-insensitively.
- [x] 2.2 Re-derive and persist `DeploymentORM.domainname` from `user_values_json` using the matched field key; persist `null` when no matching field exists.
- [x] 2.3 Add/update API unit tests for derived `domainname` persistence, including recursive match, first-match, no-match, and update re-derivation cases.

## 3. Read Contract and UI Dashboard Update

- [x] 3.1 Verify and test that `GET /deployment` responses continue returning `domainname`.
- [x] 3.2 Remove the dedicated `Domain name` TextField from the Dashboard deployment flow.
- [x] 3.3 Update UI request builders/types/tests to ensure write payloads do not include top-level `domainname`.

## 4. Parity, Docs, and Verification

- [x] 4.1 Verify API and CLI remain in lockstep for deployment write-field validation.
- [x] 4.2 Update API/UI/CLI documentation and examples to reflect write removal and read retention of `domainname`.
- [x] 4.3 Run relevant API, CLI, and UI test suites and fix regressions introduced by the contract change.
