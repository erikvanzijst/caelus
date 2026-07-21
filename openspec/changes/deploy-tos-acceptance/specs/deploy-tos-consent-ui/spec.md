## ADDED Requirements

### Requirement: Deploy dialog requires ToS agreement before launch

The deploy dialog MUST present a required "I agree to the Terms of Service"
checkbox for new deployments, and MUST keep the Launch action disabled until it
is checked (in addition to the existing launch preconditions). The agreement
text MUST link the Terms of Service and Acceptable Use Policy and reference the
Privacy Policy; only the Terms of Service requires the explicit check.

#### Scenario: Launch blocked until agreement

- **WHEN** a user opens the deploy dialog for a product and has not checked the
  agreement box
- **THEN** the Launch button is disabled

#### Scenario: Launch enabled after agreement

- **WHEN** the user checks the agreement box and all other launch preconditions
  are met
- **THEN** the Launch button becomes enabled

#### Scenario: Editing an existing deployment is unaffected

- **WHEN** the dialog is opened to edit an existing deployment (not a new
  launch)
- **THEN** the deployment-update flow is not gated by a new ToS checkbox

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

### Requirement: Displayed ToS version is submitted on create

On creating a new deployment, the UI MUST send the `version` of the Terms of
Service document it displayed to the user as part of the create request.

#### Scenario: Create payload carries the displayed version

- **WHEN** the user checks the agreement and launches a new deployment while the
  bundled Terms of Service version is `2026-07-01`
- **THEN** the create request includes `tos_version` equal to `2026-07-01`
