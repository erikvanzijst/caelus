## Purpose

Lets a client upload a project archive straight to object storage without routing the
bytes through the API, while keeping the destination and the maximum size under the
platform's control rather than the client's.

## ADDED Requirements

### Requirement: Artifact upload slots are minted on request

The system SHALL provide an authenticated endpoint that issues a single-use upload slot
for a project archive, returning an artifact identifier and the credentials needed to
upload directly to object storage.

The endpoint MUST NOT create any persistent record. An upload that is never started,
never finishes, or is abandoned therefore leaves no state to reconcile or clean up.

#### Scenario: Authenticated caller receives an upload slot

- **WHEN** an authenticated user requests an upload slot
- **THEN** the response contains a newly generated artifact identifier and the credentials required to upload the archive

#### Scenario: Anonymous caller is refused

- **WHEN** an unauthenticated request is made for an upload slot
- **THEN** the request is rejected and no slot is issued

#### Scenario: Requesting a slot creates no record

- **WHEN** a caller requests an upload slot and never uploads anything
- **THEN** no build, artifact record, or other persistent state exists as a result

### Requirement: The object key is derived from the authenticated caller

The system SHALL construct the object key for an upload slot from the authenticated
caller's identity and a server-generated artifact identifier. The client MUST NOT be able
to influence the key, and the API MUST NOT accept a caller-supplied object key, URL, or
path.

Deriving the key server-side means an artifact is bound to its uploader by construction.
There is no ownership check to bypass, and no client-supplied string whose parsing could
be subverted by traversal sequences, encoding tricks, or a substituted host.

#### Scenario: Key encodes the authenticated caller

- **WHEN** an upload slot is issued to a user
- **THEN** the object key contains that user's identifier and the generated artifact identifier

#### Scenario: Caller-supplied location is not honored

- **WHEN** a request to mint a slot includes an object key, path, or URL
- **THEN** that input is ignored or rejected, and the issued slot still points at the server-derived key

### Requirement: Upload credentials constrain destination and size

The issued credentials SHALL permit writing only to the single derived object key, and
SHALL cap the size of the uploaded object. The cap MUST be enforced by the object store
itself rather than by the client or by an intermediate proxy.

Enforcement at the store is what makes the cap real: a client that ignores it, or a proxy
configured without a body limit, cannot cause an oversized object to be stored.

#### Scenario: Upload to the issued key succeeds

- **WHEN** a client uploads an archive within the size cap using the issued credentials
- **THEN** the object store accepts the object at the derived key

#### Scenario: Upload to a different key is rejected

- **WHEN** a client attempts to upload to any key other than the one the credentials were issued for
- **THEN** the object store rejects the request

#### Scenario: Oversized upload is rejected

- **WHEN** a client attempts to upload an archive exceeding the configured size cap
- **THEN** the object store rejects the request and no object is stored

### Requirement: Upload credentials expire

The issued credentials SHALL become invalid after a configured period.

#### Scenario: Expired credentials are refused

- **WHEN** a client attempts an upload after the credentials' validity period has passed
- **THEN** the object store rejects the request

### Requirement: Artifacts expire without platform intervention

Uploaded artifacts SHALL be removed by an object lifecycle policy rather than by any
Freepod process, and incomplete uploads MUST be reclaimed the same way.

Artifacts are consumed once, moments after upload. Declarative expiry means no cleanup
job exists to fail, fall behind, or be forgotten.

#### Scenario: Artifact is expired by lifecycle policy

- **WHEN** an artifact has been stored for longer than the configured expiry period
- **THEN** it is removed without any Freepod component acting on it

#### Scenario: Abandoned upload is reclaimed

- **WHEN** a client begins a multipart upload and never completes it
- **THEN** the incomplete upload is reclaimed by the lifecycle policy
