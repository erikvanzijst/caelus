## Purpose

The client-facing surface of the build subsystem: creating a build from an uploaded
artifact, polling its status, and streaming its log output incrementally while it runs.

## ADDED Requirements

### Requirement: Builds are created from an uploaded artifact

The system SHALL provide an authenticated endpoint that creates a build from a previously
issued artifact identifier. The caller MUST supply only that identifier; the owning user
MUST be taken from the authenticated session and MUST NOT be accepted as request input.

#### Scenario: Build is created for an uploaded artifact

- **WHEN** an authenticated user creates a build referencing an artifact they uploaded
- **THEN** a build is created in `queued` status, owned by that user, and its location is returned

#### Scenario: Owner is not taken from the request body

- **WHEN** a build creation request includes a user identifier
- **THEN** that value is ignored or rejected, and the build is owned by the authenticated caller

#### Scenario: Anonymous creation is refused

- **WHEN** an unauthenticated request attempts to create a build
- **THEN** the request is rejected and no build is created

### Requirement: Build creation verifies the artifact exists

The system SHALL confirm that the referenced artifact is present in object storage before
creating the build, and SHALL reject the request with a client error if it is absent.

Without this check an upload that silently failed would surface minutes later as an
obscure fetch error inside the build container, instead of immediately at the point the
client can act on it.

#### Scenario: Missing artifact is rejected at creation time

- **WHEN** a client creates a build referencing an artifact that was never successfully uploaded
- **THEN** the request is rejected with a client error and no build is created

#### Scenario: Artifact belonging to another user is not reachable

- **WHEN** a client references an artifact identifier that resolves outside their own derived key prefix
- **THEN** the artifact is not found and the request is rejected

### Requirement: Builds are readable only by their owner

The system SHALL scope build reads to the authenticated caller's own builds.
Administrators MAY read any build. A build belonging to another user MUST be
indistinguishable from one that does not exist.

#### Scenario: Owner reads their build

- **WHEN** a user requests a build they own
- **THEN** the build's status, timestamps, artifact identifier, and image value are returned

#### Scenario: Another user's build is not found

- **WHEN** a user requests a build owned by someone else
- **THEN** the response is indistinguishable from a request for a build that does not exist

### Requirement: A user can list their own builds

The system SHALL provide an endpoint listing the authenticated caller's builds, most
recent first. Builds owned by other users MUST NOT appear. Administrators MAY list any
user's builds.

Without enumeration a client can only ever reference a build whose identifier it still
holds, so a previously produced image becomes unreachable once the client forgets it —
which is what a redeploy or a rollback needs.

#### Scenario: Caller lists their builds

- **WHEN** an authenticated user lists builds
- **THEN** their own builds are returned, most recent first

#### Scenario: Listing excludes other users' builds

- **WHEN** an authenticated user lists builds while other users also have builds
- **THEN** only the caller's own builds are returned

### Requirement: Build log is retrievable incrementally

The system SHALL expose a build's accumulated output as plain text supporting HTTP range
requests, so a client can poll for output appended since its last read without
retransferring what it already has.

Because the log grows while a build runs, a partial response MUST report an unknown total
length rather than asserting one.

#### Scenario: Client reads the log from the beginning

- **WHEN** a client requests a build's log without a range
- **THEN** the full accumulated output is returned as plain text

#### Scenario: Client polls for newly appended output

- **WHEN** a client requests a range starting at the offset it previously read to
- **THEN** only output appended since that offset is returned

#### Scenario: Client polls when nothing new has been appended

- **WHEN** a client requests a range starting at the current end of the log
- **THEN** an empty partial response is returned rather than an error, so the client's polling loop needs no special case

#### Scenario: Growing log reports unknown total length

- **WHEN** a partial log response is returned for a build that is still running
- **THEN** the response reports the total length as unknown

### Requirement: Log responses carry the build status

Every log response SHALL include the build's current status as a response header, so a
client polling for output learns when to stop without a second request.

#### Scenario: Client learns the build is still running

- **WHEN** a client reads the log of a build in `queued` or `running`
- **THEN** the response reports that status and the client continues polling

#### Scenario: Client learns the build has finished

- **WHEN** a client reads the log of a build in a terminal status
- **THEN** the response reports that status and the client stops polling

### Requirement: Build log is bounded

A build's stored output SHALL be capped at a configured size. Once the cap is reached,
further output MUST be discarded and the stored log MUST end with a marker stating that
truncation occurred.

#### Scenario: Log is truncated at the cap

- **WHEN** a build produces more output than the configured cap
- **THEN** the stored log holds at most the cap and ends with an explicit truncation marker

#### Scenario: Truncation does not fail the build

- **WHEN** a build's output is truncated
- **THEN** the build's own outcome is unaffected
