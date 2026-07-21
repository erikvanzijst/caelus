## ADDED Requirements

### Requirement: Each legal document exposes a parsed version

The UI legal-document registry MUST expose a `version` string for every
registered document, derived from that document's `**Effective date:**` line as
an ISO-8601 date (`YYYY-MM-DD`). The value MUST be parsed once from the bundled
markdown source (not hand-maintained separately), so the human-facing effective
date is the single source of truth for the version.

#### Scenario: Terms of Service version reflects its effective date

- **WHEN** the registry is loaded and the Terms of Service markdown contains
  `**Effective date:** 2026-07-01`
- **THEN** the Terms of Service entry exposes `version` equal to `2026-07-01`

#### Scenario: Version is available to consumers

- **WHEN** UI code reads the Terms of Service document from the registry
- **THEN** it can obtain the document's `version` without re-parsing the
  markdown itself

### Requirement: A missing or malformed effective date fails the build

The version parser MUST reject a document whose markdown has no valid
`YYYY-MM-DD` effective date, surfacing the failure at module load / build time
rather than yielding an empty or incorrect version at runtime. A test MUST
assert that every registered document yields a valid ISO-8601 version.

#### Scenario: Document without a parseable effective date

- **WHEN** a legal document's markdown lacks a valid `**Effective date:**` line
- **THEN** loading the registry raises an error (the dev/CI build fails) rather
  than exposing an empty or wrong `version`

#### Scenario: Guard test covers all documents

- **WHEN** the legal-content test suite runs
- **THEN** it asserts each registered document's `version` matches
  `^\d{4}-\d{2}-\d{2}$`
