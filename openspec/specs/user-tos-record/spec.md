# user-tos-record Specification

## Purpose
Record Terms of Service acceptance as a user-level fact captured once — not per
deployment — via the `/api/me/tos-acceptance` resource (POST to record, GET to
read status). Storing the accepted version and timestamp on the user gives a
durable consent record and a clean basis for a future re-approval flow
(`accepted_version < current`), while keeping acceptance off the user identity
model.
## Requirements
### Requirement: ToS acceptance is a user resource recorded once

The user MUST persist the accepted Terms of Service version and the acceptance
timestamp in nullable columns (`tos_accepted_version` as an ISO-8601 date string,
`tos_accepted_at` as a timestamp), both NULL until the user accepts. Acceptance
is recorded via `POST /api/me/tos-acceptance` and MUST be recorded once per user
regardless of how many deployments they create. The submitted version MUST equal
the API's current ToS version; a mismatch MUST be rejected with **409** (the
terms changed) and MUST NOT record acceptance. A malformed (non-`YYYY-MM-DD`)
version MUST be rejected with a validation error.

#### Scenario: Recording acceptance of the current version

- **WHEN** a user with no acceptance POSTs `/api/me/tos-acceptance` with the
  current version `2026-07-01`
- **THEN** their `tos_accepted_version` becomes `2026-07-01`, `tos_accepted_at`
  is set, and the response reports the recorded version

#### Scenario: Recording a non-current version is rejected

- **WHEN** a user POSTs a well-formed version that is not the current version
- **THEN** the API responds **409** and no acceptance is recorded

#### Scenario: Recording a malformed version is rejected

- **WHEN** a user POSTs a `version` that is not a `YYYY-MM-DD` date
- **THEN** the API responds with a validation error and no acceptance is recorded

#### Scenario: Recording is idempotent for the current version

- **WHEN** a user who already accepted the current version POSTs it again
- **THEN** the API succeeds and their acceptance remains the current version

### Requirement: The acceptance resource is always readable

`GET /api/me/tos-acceptance` MUST return **200** with the caller's acceptance
status even when they have not accepted, in which case `version` and
`accepted_at` are null. Acceptance MUST NOT be exposed as a field on the user
identity model (`GET /api/me`).

#### Scenario: Unaccepted user reads a null status

- **WHEN** a user who has never accepted calls `GET /api/me/tos-acceptance`
- **THEN** the response is 200 with `version` and `accepted_at` null

#### Scenario: Accepted user reads their version

- **WHEN** a user whose accepted version is `2026-07-01` calls
  `GET /api/me/tos-acceptance`
- **THEN** the response includes `version` equal to `2026-07-01`

### Requirement: The acceptance resource reports the currently required version

The acceptance status document MUST carry a `current_version` field holding the
version the platform currently requires (the API's current ToS version), so a
client that does not render the Terms itself — a CLI or any non-browser client
with no bundled ToS document to parse an effective date from — can learn which
value to submit. It MUST always be a non-null `YYYY-MM-DD` date, including for a
user who has never accepted, and MUST be reported independently of `version`:
`version` is what the *user* accepted (null until they do), `current_version` is
what the *platform* requires. The field MUST be present on both the GET and the
POST response, which share one status document.

#### Scenario: Unaccepted user still learns the required version

- **WHEN** a user who has never accepted calls `GET /api/me/tos-acceptance`
- **THEN** the response is 200 with `version` null and `current_version` equal to
  the API's current ToS version

#### Scenario: A user whose accepted version is stale sees both

- **WHEN** a user who accepted `2026-07-01` calls `GET /api/me/tos-acceptance`
  after the current version has moved on to `2027-01-01`
- **THEN** the response reports `version` `2026-07-01` and `current_version`
  `2027-01-01`, and POSTing the reported `current_version` is accepted while the
  stale `version` is rejected with **409**

#### Scenario: Recording returns the required version too

- **WHEN** a user POSTs `/api/me/tos-acceptance` with the current version
- **THEN** the response carries `current_version`, equal to the just-recorded
  `version`

### Requirement: CLI parity for recording acceptance

The CLI MUST provide an `accept-tos` command mirroring `POST /api/me/tos-acceptance`
(a `--version` equal to the current ToS version, recording acceptance on the
target user), so operators can satisfy the deployment precondition.

#### Scenario: CLI records acceptance

- **WHEN** an operator runs `accept-tos --user-id <id> --version 2026-07-01`
- **THEN** that user's acceptance is recorded as `2026-07-01`

