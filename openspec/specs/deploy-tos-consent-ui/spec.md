# deploy-tos-consent-ui Specification

## Purpose
TBD - created by archiving change deploy-tos-acceptance. Update Purpose after archive.
## Requirements
### Requirement: Deploy dialog requires ToS agreement only from users who have not accepted

The deploy dialog MUST present a required "I agree to the Terms of Service"
checkbox for new deployments **only when** the current user has not yet accepted
the current Terms of Service (per `GET /api/me/tos-acceptance`), and MUST keep the
Launch action disabled until it is checked (in addition to the existing launch
preconditions). When the user has **already** accepted, the dialog MUST NOT show
the checkbox and MUST NOT gate Launch on it. The agreement text MUST link the
Terms of Service and Acceptable Use Policy and reference the Privacy Policy; only
the Terms of Service requires the explicit check.

#### Scenario: Unaccepted user is blocked until agreement

- **WHEN** a user who has not accepted opens the deploy dialog and has not checked
  the agreement box
- **THEN** the checkbox is shown and the Launch button is disabled

#### Scenario: Unaccepted user enables launch by agreeing

- **WHEN** such a user checks the agreement box and all other launch
  preconditions are met
- **THEN** the Launch button becomes enabled

#### Scenario: Already-accepted user sees no checkbox

- **WHEN** a user whose `/api/me/tos-acceptance` reports an accepted version opens
  the deploy dialog
- **THEN** no agreement checkbox is shown and Launch is gated only by the existing
  preconditions

#### Scenario: Editing an existing deployment is unaffected

- **WHEN** the dialog is opened to edit an existing deployment (not a new launch)
- **THEN** the deployment-update flow is not gated by a ToS checkbox

### Requirement: Reading the ToS preserves deploy dialog state

The user MUST be able to open and read the full Terms of Service from within the
deploy dialog without losing values already entered in the form. Opening the
document MUST NOT navigate away from or unmount the deploy dialog.

#### Scenario: Open and close the ToS while filling the form

- **WHEN** the user has entered a hostname, opens the Terms of Service from the
  agreement text, reads it, and closes it
- **THEN** the deploy dialog reappears with the previously entered hostname and
  any other input intact

#### Scenario: ToS reader reuses the shared document renderer

- **WHEN** the Terms of Service is opened from the deploy dialog
- **THEN** its content is rendered by the same shared legal-document body
  component used by the full-page legal route (no duplicate renderer)

### Requirement: First launch records acceptance before deploying

The UI MUST, when a user who has not yet accepted checks the agreement and
launches, first record acceptance via `POST /api/me/tos-acceptance` (sending the
version of the Terms it displayed) and then create the deployment. When the user
has already accepted, the UI MUST create the deployment directly without an
acceptance call.

#### Scenario: Unaccepted user's launch records then deploys

- **WHEN** a user who has not accepted checks the agreement and launches while the
  bundled Terms of Service version is `2026-07-01`
- **THEN** the UI records acceptance of `2026-07-01` and then creates the
  deployment

#### Scenario: Accepted user's launch deploys directly

- **WHEN** a user who has already accepted launches a new deployment
- **THEN** the UI creates the deployment without a further acceptance call

