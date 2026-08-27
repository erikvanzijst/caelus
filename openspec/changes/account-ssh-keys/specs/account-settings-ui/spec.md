## Purpose

The web UI has no account-level surface: it offers a dashboard of deployments, an admin
area for privileged users, and the legal pages. Anything that belongs to the person
rather than to one deployment has nowhere to live. This capability introduces an account
settings page reachable from the app shell, and its first panel — managing the SSH public
keys that authenticate the account. The page is designed to hold more than keys later,
so its structure is the durable part and the keys panel is its first occupant.

## ADDED Requirements

### Requirement: An account settings page exists and is reachable from the app shell
The application MUST provide an account settings page at its own route, available to every authenticated user regardless of privilege, and MUST make it reachable from the app shell's existing account menu — the same menu that already offers the admin area and sign-out.

The page MUST be structured so that further account-level sections can be added without rework, following the pattern the admin area already uses for its panels rather than inventing a second one.

The entry MUST NOT be presented as an administrative feature: it is the ordinary user's own account, and a non-privileged user MUST see it.

#### Scenario: Ordinary user reaches settings
- **WHEN** a signed-in user without administrator privileges opens the account menu
- **THEN** an entry leading to account settings is present, and following it opens the settings page

#### Scenario: Settings is not gated on privilege
- **WHEN** a user without administrator privileges navigates directly to the settings route
- **THEN** the settings page renders

#### Scenario: Unauthenticated access is handled like the rest of the application
- **WHEN** an unauthenticated visitor navigates to the settings route
- **THEN** they are handled exactly as they are for other authenticated routes, with no settings content disclosed

### Requirement: The SSH keys panel is its own component
The SSH keys panel MUST be implemented as its own component under the components directory, not inlined into the settings page, so that the page remains a composition of sections. This follows the project's standing rule that functionality is extracted into focused, single-responsibility components rather than accumulating in page-level ones.

#### Scenario: Panel is reusable
- **WHEN** the settings page renders
- **THEN** the SSH keys section is supplied by a dedicated component that the page composes

### Requirement: The panel lists registered keys with what is needed to revoke the right one
The panel MUST list the account's registered keys, showing for each the label, the fingerprint, the key type and when it was registered. Fingerprints MUST be displayed in the same `SHA256:` form the platform and standard SSH tooling use, so a user can compare what they see against their own machine.

An account with no keys MUST be shown an explanatory empty state that says what keys are for and how to add one, not a bare empty list.

#### Scenario: Keys are listed
- **WHEN** a user with registered keys opens the settings page
- **THEN** each key is listed with its label, fingerprint, type and registration time

#### Scenario: Empty state explains itself
- **WHEN** a user with no registered keys opens the panel
- **THEN** an explanatory empty state is shown, including how to add a key

### Requirement: Adding a key accepts a pasted public key and an optional label
The panel MUST let a user add a key by pasting a public key in OpenSSH single-line format, with an optional label. It MUST surface the platform's validation failures — unsupported type, malformed key, duplicate, private key material, account limit reached — as distinct, readable messages rather than a generic failure.

The panel MUST warn the user before submission if the pasted content looks like a private key, and MUST NOT submit it.

#### Scenario: Valid key is added
- **WHEN** a user pastes a valid public key and submits
- **THEN** the key is registered and appears in the list with its fingerprint

#### Scenario: Rejection is explained
- **WHEN** the platform rejects a submission because the key is a duplicate
- **THEN** the panel says the key is already registered, distinguishably from other failures

#### Scenario: Private key is caught before submission
- **WHEN** a user pastes private key material into the field
- **THEN** the panel warns that this is a private key and does not submit it

#### Scenario: Limit is communicated before it is hit
- **WHEN** the account is at or near the platform's key limit
- **THEN** the panel communicates the limit, using the value reported by the platform rather than one built into the application

### Requirement: Deleting a key is confirmed and states its consequence
Deleting a key MUST require an explicit confirmation that identifies the key being removed and states the consequence: any machine holding that key loses access. Deletion is how a user revokes a lost device, so the panel MUST NOT make it hard to find — but it MUST NOT be a single unguarded click either.

#### Scenario: Deletion is confirmed
- **WHEN** a user chooses to delete a key
- **THEN** a confirmation identifying that key and its consequence is shown before anything is removed

#### Scenario: Confirmed deletion removes the key
- **WHEN** the user confirms
- **THEN** the key is removed and disappears from the list

### Requirement: The UI never accepts or displays private key material
No part of the settings surface may display, store, or transmit an SSH private key, and the panel MUST NOT offer to generate a keypair in the browser. Key generation belongs where the private half can stay on the user's machine.

#### Scenario: No private material is rendered
- **WHEN** any part of the SSH keys panel renders
- **THEN** no private key material is shown

#### Scenario: No in-browser generation
- **WHEN** a user looks for a way to create a key from the panel
- **THEN** the panel directs them to the client instead of generating one in the browser
