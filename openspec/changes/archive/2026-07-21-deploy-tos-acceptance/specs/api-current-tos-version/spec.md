## ADDED Requirements

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
