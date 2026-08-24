## ADDED Requirements

### Requirement: A release reports the vars it ran with
A release read SHALL report the vars bound to that release — its snapshot, not the
deployment's current head — using the same wire shape and the same omission rule for
sensitive values as every other read.

Reporting the snapshot is what makes a release answer "what was this actually running",
which is the question a release read exists for, and it stays correct after the
deployment's vars have since changed.

#### Scenario: Reading a release
- **WHEN** a caller reads a release whose snapshot holds two vars
- **THEN** the response carries those two vars
- **AND** any sensitive one carries no value

#### Scenario: Reading an old release after a change
- **WHEN** a var is changed and a caller reads the earlier release
- **THEN** that release reports the value it ran with, not the current one

#### Scenario: A release with no vars
- **WHEN** a caller reads a release whose snapshot is empty
- **THEN** the response reports no vars
