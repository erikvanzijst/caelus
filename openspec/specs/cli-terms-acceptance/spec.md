# cli-terms-acceptance Specification

## Purpose
How the client settles Terms of Service acceptance: where it asks, where it merely
offers, and why the version it submits is never one it carries.
## Requirements
### Requirement: Acceptance is settled before a build is spent

The platform refuses to create a deployment for an account that has not accepted its
terms, and that refusal arrives from the creation request — after the archive has been
packed, uploaded, and built. The client SHALL therefore establish acceptance during
deploy preflight, before packing.

Acceptance gates creation only, so the client SHALL ask only when it is about to create
a deployment, and SHALL NOT ask when updating an existing one.

#### Scenario: An unaccepted first deploy is stopped before anything is built

- **WHEN** a deploy would create a deployment for an account that has not accepted
- **THEN** the client settles acceptance before packing
- **AND** no archive is packed and no build is created

#### Scenario: An update never asks

- **WHEN** a deploy updates an existing deployment
- **THEN** the client does not read or ask about acceptance

#### Scenario: A deploy that cannot succeed anyway does not ask

- **WHEN** a cheaper preflight check has already established that the deploy cannot
  succeed
- **THEN** the client refuses on that ground and never presents the terms

### Requirement: The accepted version is learned from the platform

The version submitted when recording acceptance SHALL be the one the platform reports as
current. The client SHALL NOT carry its own copy of it.

The current version is a release constant of the API image while the client ships on its
own cadence, so an embedded copy would be refused for every user of that client from the
first revision of the terms onward, locking them out of deploying entirely.

Where the platform does not report a current version, the client SHALL NOT guess one,
SHALL NOT present an agreement it cannot record, and SHALL direct the user to accept in
the web interface.

#### Scenario: The reported version is what gets recorded

- **WHEN** a user accepts and the platform reports a current version
- **THEN** the client submits exactly that version

#### Scenario: An unreported version is not guessed

- **WHEN** the platform does not report a current version
- **THEN** the client presents nothing, submits nothing, and names where to accept

### Requirement: The client presents the same agreement as the web interface

Before asking, the client SHALL name all three legal documents and give a location for
each, on the environment being deployed to. The wording of the agreement SHALL match the
web interface's, because the wording is the consent record.

#### Scenario: The documents are offered before the question

- **WHEN** the client asks a user to accept
- **THEN** all three documents are named and located first

#### Scenario: The documents are those of the target environment

- **WHEN** the client presents the terms for a given environment
- **THEN** the locations it gives are that environment's

### Requirement: Authentication offers acceptance but is never gated on it

Logging in SHALL offer to settle acceptance when it is outstanding, and SHALL complete
successfully whether or not the user accepts. Authentication also serves automation and
read-only use, which acceptance is not a precondition for.

#### Scenario: Login completes after a decline

- **WHEN** a user logs in, is offered the terms, and declines
- **THEN** the login succeeds and reports that the terms are outstanding

#### Scenario: A non-interactive login neither asks nor fails

- **WHEN** a login runs with no terminal to ask on
- **THEN** nothing is asked, nothing is recorded, and the login succeeds

### Requirement: A refusal names its own cause

A deploy that cannot proceed for want of acceptance SHALL report which of the possible
causes applies — the user declined, there was no terminal to ask on, or the platform did
not report a version — and SHALL NOT report one as another.

#### Scenario: A platform gap is not reported as a decline

- **WHEN** a user agrees but the platform reports no current version
- **THEN** the client reports the platform's silence, not the user's answer

#### Scenario: A refusal states nothing was built

- **WHEN** a deploy stops because acceptance was not settled
- **THEN** the client states that nothing has been built or deployed

