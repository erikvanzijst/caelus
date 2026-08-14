# build-data-model Specification

## Purpose
Defines the build record: what a build is, who owns it, the states it moves through, and
the identifiers that tie it to its uploaded artifact and its resulting container image.
## Requirements
### Requirement: Builds are owned by a user, not a deployment

A build SHALL be owned by the user who created it. A build MUST NOT reference a
deployment. The system MUST NOT restrict how many builds a user may create, nor relate
concurrent builds to one another.

Builds transform a project archive into a container image. Which deployment, if any,
consumes that image is decided separately by the client: a deployment may consume several
images, and most products consume none.

#### Scenario: Build records its owner

- **WHEN** a build is created by an authenticated user
- **THEN** the build records that user as its owner

#### Scenario: Build carries no deployment reference

- **WHEN** a build record is read
- **THEN** it exposes no deployment identifier, and no deployment is implied by its existence

#### Scenario: A user runs two builds at once

- **WHEN** a user creates a second build while a first is still running
- **THEN** both builds are accepted and proceed independently, and neither supersedes the other

### Requirement: Build state machine

A build SHALL occupy exactly one of the states `queued`, `running`, `succeeded`,
`failed`, or `canceled`.

Permitted transitions are `queued → running`, `running → succeeded`, and
`running → failed`. `succeeded`, `failed`, and `canceled` are terminal. A failed build
MUST NOT be retried automatically; recovery is creating a new build.

The `canceled` state is reserved. No operation in this change transitions a build into it.

#### Scenario: Newly created build is queued

- **WHEN** a build is created
- **THEN** its status is `queued` and both its start and finish timestamps are unset

#### Scenario: Terminal states are final

- **WHEN** a build has reached `succeeded`, `failed`, or `canceled`
- **THEN** no subsequent operation changes its status

#### Scenario: Failure is not retried

- **WHEN** a build reaches `failed`
- **THEN** the system does not re-run it, and the build's Kubernetes Job is not recreated

### Requirement: Build exposes its resulting image only on success

A build SHALL expose an `image` value that is null until the build reaches `succeeded`,
at which point it MUST carry the reference `{user_id}@{digest}` — a container image
reference with the registry host removed.

The value MUST be a flat string, not a structured object. It is submitted verbatim by the
client as a product's `image` user value, so any reassembly by the client would be a place
for the two subsystems to diverge on format.

#### Scenario: Image is absent before success

- **WHEN** a build is in `queued`, `running`, or `failed`
- **THEN** its `image` value is null

#### Scenario: Image is present after success

- **WHEN** a build reaches `succeeded`
- **THEN** its `image` value is the string `{user_id}@sha256:<64 lowercase hex characters>`, where `{user_id}` is the build's owner

### Requirement: An artifact has at most one build in flight

The system SHALL permit at most one non-terminal build per artifact. Creating a build for
an artifact whose existing build is `queued` or `running` MUST return that existing build
rather than creating a second one. Creating a build for an artifact whose builds have all
reached a terminal status MUST create a new build.

This makes creation idempotent over the window in which retries actually occur — a client
retrying a request whose response was lost does so within seconds, while its original build
is certainly still non-terminal — without forbidding a rebuild of the same source.

Rebuilding matters because build failures are often transient: a package registry timeout,
a memory-exhausted node, a registry push that did not complete. Requiring the client to
re-upload an identical archive to retry would waste the upload for no benefit. How long a
rebuild remains possible is bounded naturally by the artifact's own expiry.

#### Scenario: Retry while a build is in flight returns the existing build

- **WHEN** a client creates a build for an artifact whose build is `queued` or `running`
- **THEN** the existing build is returned and no second build is created

#### Scenario: Rebuild after failure is allowed

- **WHEN** a client creates a build for an artifact whose previous build reached `failed`
- **THEN** a new build is created for the same artifact

#### Scenario: Rebuild after success is allowed

- **WHEN** a client creates a build for an artifact whose previous build reached `succeeded`
- **THEN** a new build is created for the same artifact

### Requirement: Build records its Kubernetes Job and log

A build SHALL record the identifier of the Kubernetes Job created for it, null until that
Job exists, and SHALL accumulate the Job's output as text.

The Job identifier is what lets a worker other than the one that started a build
determine that build's true outcome.

#### Scenario: Job identifier is absent before the Job exists

- **WHEN** a build is `queued`, or is `running` but its Job has not yet been created
- **THEN** its Job identifier is null

#### Scenario: Job identifier is recorded once the Job exists

- **WHEN** a Kubernetes Job has been created for a build
- **THEN** the build records that Job's identifier

