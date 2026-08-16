# cli-delete Specification

## Purpose
Removing a project's deployment from the command line: what the client refuses to
address, what it insists on being told before destroying anything, and how it reports a
teardown that the platform performs asynchronously.
## Requirements
### Requirement: Deletion addresses only the deployment the project records

The client SHALL delete the deployment recorded in the project file for the targeted
environment, and SHALL NOT accept a deployment named by the caller. A command able to
name an arbitrary deployment is one whose worst mistake is unrecoverable, and the
project file is the only place the client knows a deployment by.

When no project file is found, when the project file records no deployment, or when the
project belongs to a different environment than the command targets, the client SHALL
refuse with a usage error and SHALL delete nothing.

The client SHALL establish the authenticated account before reading the deployment, so
that a credential problem is reported as one rather than surfacing later as a missing
deployment.

#### Scenario: A directory that is not a project is refused

- **WHEN** deletion runs where no project file exists
- **THEN** the client refuses with a usage error and names how to initialize a project

#### Scenario: A project that has never deployed has nothing to delete

- **WHEN** deletion runs in a project whose file records no deployment
- **THEN** the client refuses with a usage error
- **AND** no request is made to the platform

#### Scenario: A project belonging to another environment is refused

- **WHEN** deletion targets one environment and the project file belongs to another
- **THEN** the client refuses and names the environment the project belongs to

#### Scenario: The credential is exercised before the deployment is read

- **WHEN** deletion runs
- **THEN** the authenticated account is established before the deployment is read

### Requirement: Nothing is deleted without an explicit answer

The client SHALL describe what is about to be destroyed — the deployment's name, and its
address where it has one — and SHALL require confirmation before requesting the
deletion. A generated name is not recognizable on its own; the address is what the user
knows the deployment by.

Confirmation MAY be given in advance so the command can run unattended. Where no
confirmation has been given in advance and no interactive answer can be obtained, the
client SHALL refuse and SHALL delete nothing: a run that deletes because nobody was
present to object is not an acceptable outcome.

A declined confirmation SHALL leave the deployment and the project file untouched, and
SHALL NOT be reported as a failure. The user was asked and answered.

Where diagnostics are suppressed, the confirmation question itself SHALL still identify
the deployment, so that suppressing output can never turn the question into a blind one.

#### Scenario: The user is shown what they are about to lose

- **WHEN** deletion asks for confirmation
- **THEN** the deployment's name and address are shown
- **AND** the user is told that the deployment and everything it stores are destroyed

#### Scenario: A decline changes nothing

- **WHEN** the user declines the confirmation
- **THEN** no deletion is requested
- **AND** the project file still records the deployment
- **AND** the command reports success, not failure

#### Scenario: An unattended run without advance confirmation refuses

- **WHEN** deletion runs with no way to ask and no confirmation given in advance
- **THEN** the client refuses with a usage error naming how to confirm in advance
- **AND** nothing is deleted

#### Scenario: Confirming in advance asks nothing

- **WHEN** deletion runs with confirmation given in advance
- **THEN** no question is presented and the deletion proceeds

### Requirement: The deployment pointer is discarded once the platform accepts the deletion

The client SHALL remove the deployment pointer from the project file as soon as the
platform accepts the deletion, and SHALL do so before waiting for the teardown to
finish. From that moment the deployment can never serve the project again, so retaining
the pointer would only make the next deploy fail against something the user has already
asked to be rid of — and an interrupted wait must not leave the pointer behind.

Everything else in the project file SHALL be retained. The recorded values are the
user's intent rather than the deployment's state, so a later deploy SHALL be able to
recreate the application under the same hostname without being asked again.

Where the platform refuses the deletion, the pointer SHALL be retained, because it still
describes a deployment that exists.

#### Scenario: A successful deletion clears only the pointer

- **WHEN** the platform accepts the deletion
- **THEN** the project file no longer records a deployment
- **AND** the recorded user values are unchanged

#### Scenario: The pointer is cleared before the teardown is awaited

- **WHEN** the platform accepts the deletion and the subsequent wait does not complete
- **THEN** the project file no longer records a deployment

#### Scenario: A refused deletion keeps the pointer

- **WHEN** the platform refuses the deletion
- **THEN** the project file still records the deployment

### Requirement: A deployment already gone, or already going, is not deleted twice

The client SHALL treat a deployment the platform no longer has, and one the platform
reports as being torn down or torn away, as an accepted outcome rather than an error: in
each case the stale pointer SHALL be cleared and no second deletion SHALL be requested.

Where the platform reports a deletion already under way, the client SHALL NOT ask for
confirmation. The destructive decision was made earlier, and asking again would imply
this run could still prevent it.

#### Scenario: A deployment deleted elsewhere leaves only a stale pointer

- **WHEN** the recorded deployment no longer exists on the platform
- **THEN** the client reports that it is already gone
- **AND** clears the pointer without requesting a deletion

#### Scenario: A teardown already under way is not re-confirmed

- **WHEN** the recorded deployment is already being torn down
- **THEN** the client asks nothing, requests no deletion, and clears the pointer

#### Scenario: A deployment that disappears mid-command is a success

- **WHEN** the platform reports the deployment as absent when the deletion is requested
- **THEN** the client treats the deletion as accomplished

### Requirement: The teardown is followed to completion by default

Teardown is asynchronous: acceptance schedules it, and the deployment's hostname remains
claimed until it completes. The client SHALL therefore follow the teardown until the
deployment is gone before reporting success, so that a deletion followed immediately by
a deploy cannot collide with the deployment it just removed. Following the teardown MAY
be waived by the caller, in which case the client SHALL say that the teardown continues
and that the hostname remains claimed.

Where the platform reports the teardown as failed, the client SHALL report that failure
together with the reason the platform recorded, rather than continuing to wait for an
outcome the platform has abandoned.

Where the client stops waiting before the teardown completes, it SHALL report that the
deletion was not canceled and is still proceeding. A wait that elapses is a bound on the
client's patience, never a statement about the platform.

#### Scenario: A completed teardown is reported as done

- **WHEN** the platform completes the teardown
- **THEN** the client reports the deployment as deleted

#### Scenario: A failed teardown is reported rather than waited out

- **WHEN** the platform reports the teardown as failed
- **THEN** the client reports the failure and the platform's recorded reason

#### Scenario: Waiving the wait says what remains outstanding

- **WHEN** the caller waives following the teardown
- **THEN** the client reports that teardown continues and the hostname stays claimed

#### Scenario: Giving up waiting is not a failed deletion

- **WHEN** the client stops waiting before the teardown completes
- **THEN** it reports that the deletion was not canceled and is still proceeding

### Requirement: Deletion produces no result on standard output

Deletion SHALL write nothing to standard output. Its confirmation, its progress, and its
conclusion are all diagnostics, because a deletion has no result a caller could consume.

#### Scenario: A pipeline receives nothing from a deletion

- **WHEN** a deletion completes
- **THEN** standard output is empty
