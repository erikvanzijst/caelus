# build-execution Specification

## Purpose
The contract honored by the container that performs a build: how it obtains the project
archive, produces an image, reports the result, and the boundaries it runs within given
that it executes code supplied by a tenant.
## Requirements
### Requirement: The build container holds no platform credentials

The build container SHALL NOT be given database credentials, Kubernetes API credentials,
or any long-lived registry or object-store credential.

The container executes tenant-supplied code: a project's dependency install scripts and
build commands run with full access to the container's environment. Any credential
present there is a credential handed to every tenant. This is why the build container
reports its result indirectly rather than writing to the database itself.

#### Scenario: No database access from the build container

- **WHEN** the build container's environment is inspected
- **THEN** it contains no database connection string or credential, and the database is unreachable from it

#### Scenario: No Kubernetes API access from the build container

- **WHEN** the build container attempts to reach the Kubernetes API
- **THEN** it has no credential to authenticate with

### Requirement: Network reach is restricted to what a build needs

The build container SHALL be permitted egress only to the object store, the container
registry, DNS, and public networks required to fetch dependencies. It MUST NOT be able to
reach the platform's own services or other tenants' workloads.

#### Scenario: Platform services are unreachable

- **WHEN** the build container attempts to connect to a platform service such as the database or the API
- **THEN** the connection is refused

#### Scenario: Dependency fetching still works

- **WHEN** a build installs dependencies from public package registries
- **THEN** those requests succeed

### Requirement: The artifact is retrieved with a time-limited credential

The build container SHALL retrieve its project archive using a credential supplied to it
that grants read access to that one object and expires.

#### Scenario: Artifact is retrieved and unpacked

- **WHEN** the build container starts with a valid artifact credential
- **THEN** it retrieves and unpacks the archive into its working directory

#### Scenario: Unretrievable artifact fails the build

- **WHEN** the artifact cannot be retrieved
- **THEN** the container terminates unsuccessfully, and the reason appears in its output

### Requirement: Archive extraction is constrained

The build container SHALL reject archive entries that would write outside the extraction
directory, and SHALL bound the total extracted size and entry count.

The archive is supplied by a tenant and is untrusted input. Path traversal entries,
absolute paths, escaping symbolic links, and decompression bombs must not be honored
merely because extraction happens inside a sandbox.

#### Scenario: Traversing entry is rejected

- **WHEN** an archive contains an entry resolving outside the extraction directory
- **THEN** extraction fails and the build terminates unsuccessfully

#### Scenario: Oversized archive is rejected

- **WHEN** an archive expands beyond the configured extracted-size or entry-count limit
- **THEN** extraction stops and the build terminates unsuccessfully

### Requirement: The image is produced by zero-configuration detection

The build container SHALL detect the project's stack and produce a container image without
requiring a Dockerfile or any build configuration in the project.

The build plan and the component executing it MUST be version-matched, since the plan
format is a contract between them.

#### Scenario: Project without a Dockerfile builds

- **WHEN** a project in a supported stack is built and contains no Dockerfile
- **THEN** its stack is detected and an image is produced

#### Scenario: Undetectable project fails clearly

- **WHEN** a project's stack cannot be detected
- **THEN** the build terminates unsuccessfully and its output states that detection failed

### Requirement: The image is pushed under the owner's namespace and anchored by a tag

The build container SHALL push the produced image to a repository derived from the build's
owner, under a tag derived from the build identifier, and SHALL obtain the resulting
content digest.

The tag is never exposed through the API and nothing deploys by it. It exists so the
manifest is not left untagged: an untagged manifest is removable by a registry garbage
collection pass, which would silently break every deployment referencing it by digest.

#### Scenario: Image is pushed under the owner's repository

- **WHEN** a build succeeds for a given owner
- **THEN** the image is present in the registry under that owner's repository, reachable by its digest

#### Scenario: Pushed manifest is tagged

- **WHEN** a build succeeds
- **THEN** the pushed manifest carries a tag derived from the build identifier

### Requirement: The build reports its result without credentials

On success the build container SHALL report the produced image reference through its
termination status, in the form `{user_id}@{digest}`. On any failure it SHALL terminate
with a non-zero exit status.

#### Scenario: Successful build reports its image

- **WHEN** a build completes successfully
- **THEN** the container exits successfully and its termination status carries the image reference

#### Scenario: Failed build exits non-zero

- **WHEN** any stage of the build fails
- **THEN** the container exits with a non-zero status and reports no image

### Requirement: Build output is human-readable progress

The build container SHALL emit its progress to standard output as plain text without
terminal control sequences, since that output is stored and replayed to users verbatim.

#### Scenario: Output is free of control sequences

- **WHEN** a build's stored log is read
- **THEN** it contains plain readable text with no terminal escape sequences

