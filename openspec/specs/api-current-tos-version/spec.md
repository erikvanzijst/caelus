# api-current-tos-version Specification

## Purpose
Give the API a single, authoritative notion of the *current* Terms of Service
version — a code-default release constant (`settings.current_tos_version`) — so it
can validate submitted acceptances without ever importing the ToS text (which is
UI-owned). A CI test binds this constant to the ToS markdown's effective date so
the two cannot silently drift.
## Requirements
### Requirement: The API exposes a current ToS version as a release constant

The API MUST expose a `current_tos_version` setting holding the current Terms of
Service effective date (`YYYY-MM-DD`). It MUST have a default defined in code
(`api/app/config.py`) and MUST NOT depend on being set per environment: dev and
prod running the same release share the same value. The API MUST NOT import or
render the ToS document text to obtain it — only the date string.

#### Scenario: Current version is available without configuration

- **WHEN** the API runs with no `CAELUS_CURRENT_TOS_VERSION` environment override
- **THEN** `settings.current_tos_version` equals the in-code default (the current
  ToS effective date)

### Requirement: CI asserts the API constant matches the ToS document

A test in `api/` MUST parse the effective date from the canonical Terms of
Service markdown (`ui/src/content/legal/terms-of-service.md`) and assert it
equals `settings.current_tos_version`, so the code-side constant cannot silently
drift from the document it represents.

#### Scenario: Matching constant passes

- **WHEN** `settings.current_tos_version` equals the ToS markdown's
  `**Effective date:**`
- **THEN** the guard test passes

#### Scenario: Drift fails the build

- **WHEN** the ToS markdown's effective date is changed without updating
  `settings.current_tos_version` (or vice-versa)
- **THEN** the guard test fails

### Requirement: The current ToS version is readable by clients

The current ToS version MUST be readable over the API, as the `current_version`
field of the `/api/me/tos-acceptance` status document, so clients never have to
hardcode it. Because it is a release constant of the API image, a client that
hardcoded it would be rejected with **409** the moment the terms are revised;
reading it back is the only way for a client that ships on its own cadence — a
CLI, or any client without the UI's bundled ToS markdown — to submit an
acceptance that the API will accept. The API MUST serve the value it validates
against, never a separately maintained copy.

#### Scenario: A non-browser client reads the version to submit

- **WHEN** a client with no bundled ToS document calls
  `GET /api/me/tos-acceptance` and POSTs back the `current_version` it read
- **THEN** the acceptance is recorded (the value served is exactly the value
  validated against)

#### Scenario: A revised release moves the served value

- **WHEN** the terms are revised and `settings.current_tos_version` is bumped in
  a new API release
- **THEN** `current_version` served by the API reports the new version, without
  any client release

