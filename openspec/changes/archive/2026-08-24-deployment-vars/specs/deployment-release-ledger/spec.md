## ADDED Requirements

### Requirement: A release freezes the deployment's vars when it is created
Creating a release SHALL bind, to that release, the var rows that are in the
deployment's head at that moment, in the same transaction that creates the release row.
Tombstoned keys SHALL NOT be bound.

Where the request that creates the release also submits vars, those vars SHALL be written
before the binding is taken, so the release captures them.

A var row SHALL be inserted only when the submitted value or sensitivity actually differs
from head. Without that, every rollout would append a complete copy of the configuration
and the history would stop being readable.

The binding, like every other release column, SHALL NOT be revised after it is written.

#### Scenario: A rollout captures the current vars
- **WHEN** a release is created for a deployment whose head holds three vars
- **THEN** that release is bound to those three var rows

#### Scenario: A rollout that also submits vars
- **WHEN** a release is created by a request that submits a changed var
- **THEN** the new value is written first
- **AND** the release is bound to the new value, not the previous one

#### Scenario: A rollout that changes nothing
- **WHEN** a release is created by a request submitting vars identical to head
- **THEN** no new var rows are written
- **AND** the release is bound to the existing rows

#### Scenario: A deleted key
- **WHEN** a release is created after a key was deleted
- **THEN** that key is not bound to the release

### Requirement: A failed rollout leaves the deployment's vars in place
Vars written by a request that creates a release SHALL remain the deployment's desired
state whether or not the resulting rollout succeeds, and SHALL be captured by the next
release.

This matches how the deployment's user values already behave: they are written when the
rollout is requested, not when it succeeds. Vars are desired state, and making them
conditional on a rollout's outcome would mean the platform stops recording what the user
asked for, leaving a retry with nothing to reconstruct intent from.

Nothing is lost: the failed release keeps its own binding, so what that release meant does
not change retroactively, and `pending` continues to report that the running pod does not
carry the change.

#### Scenario: A rollout fails
- **WHEN** a release carrying a changed var fails
- **THEN** head still holds the changed var
- **AND** the failed release's snapshot still resolves to what it was created with
- **AND** the deployment reports `pending` as true
