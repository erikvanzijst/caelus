## Purpose

The contract between the platform and a tenant's container image: how object-storage
credentials reach a pod, what environment variables an application may rely on, and the
guarantee that an unmodified S3 SDK works against them without any configuration.

## ADDED Requirements

### Requirement: Credentials reach the pod through a Secret, never through Helm values

The access key secret SHALL be delivered to the deployment's namespace as a Kubernetes Secret
written directly by the platform. It SHALL NOT be passed as a Helm value.

Helm values are logged in full by the platform and are persisted by Helm itself into a release
Secret in the tenant's own namespace, so a credential routed through them is written to at
least two places that outlive the request and are not access-controlled as credentials. Only
non-secret references — the Secret's name, the bucket name, the endpoint, the region — SHALL
travel through Helm values.

The Secret SHALL be created before the Helm release is installed or upgraded, so that the
release never waits on a Secret that does not yet exist.

#### Scenario: The secret access key is absent from Helm values

- **WHEN** the merged Helm values for a storage-enabled deployment are inspected
- **THEN** they contain the bucket name, endpoint, region and the Secret's name
- **AND** they do not contain the secret access key

#### Scenario: The secret access key is absent from platform logs

- **WHEN** a storage-enabled deployment is reconciled and the platform's logs are inspected
- **THEN** the secret access key does not appear in them

#### Scenario: Ordering

- **WHEN** a storage-enabled deployment is applied
- **THEN** the credentials Secret exists before the Helm release is installed or upgraded

### Requirement: The chart projects a conventional environment contract into the application container

A chart that consumes object storage SHALL project the credentials Secret into the application
container as environment variables, using the conventional names an S3 SDK already recognizes
rather than platform-specific ones:

- the access key id, secret access key and region under their standard `AWS_*` names
- the S3 endpoint under the standard endpoint variable an SDK reads natively, and under the
  generic endpoint variable as well
- the bucket name, which is platform-generated and cannot be guessed by the application

The bucket name SHALL be supplied as an environment variable and SHALL NOT be a value the
application is expected to hard-code. This keeps tenant code portable: the same image runs
against a different bucket, or a different provider, without modification.

This mirrors the existing `PORT` convention, where the platform tells the application what to
use rather than requiring the application to know.

#### Scenario: A storage-enabled pod receives the contract

- **WHEN** the application container of a storage-enabled deployment is inspected
- **THEN** it has environment variables carrying the access key id, secret access key, region,
  endpoint and bucket name
- **AND** their values match the credentials and bucket provisioned for that deployment

#### Scenario: A deployment without storage receives nothing

- **WHEN** the application container of a deployment whose product did not opt in is inspected
- **THEN** it has no object-storage environment variables
- **AND** the container starts normally

### Requirement: An unmodified S3 client works with no configuration

An application that constructs a default S3 client, supplying no endpoint, credentials or
addressing configuration of its own, SHALL be able to read and write its bucket.

The endpoint SHALL be published to tenants as the platform's public S3 hostname, and SHALL be
reachable both from inside a tenant pod and from an end user's browser, so that a single value
works for direct object access and for presigned URLs alike.

The store is addressed in **path style**. Where an SDK does not select path style
automatically for a custom endpoint, that SDK's required setting SHALL be documented for
tenants; it SHALL NOT be worked around by publishing a second endpoint or by enabling
virtual-host addressing, which would place bucket hostnames outside the platform's wildcard
certificate.

#### Scenario: Default client construction

- **WHEN** an application constructs a default S3 client with no arguments and reads or writes
  an object in its bucket
- **THEN** the operation succeeds

#### Scenario: The endpoint is reachable from a tenant pod

- **WHEN** a tenant pod, subject to the platform's baseline network isolation, connects to the
  published S3 endpoint
- **THEN** the connection succeeds and the object store responds

### Requirement: Presigned URLs minted by a tenant application are directly usable by a browser

An application SHALL be able to mint a presigned URL for an object in its own bucket and hand
it to an end user, and that URL SHALL be fetchable by an ordinary browser with no credentials
and no platform involvement.

The bucket name appears in the URL path. This is acceptable and intended: the name is derived
from the deployment identifier, which is not a secret, and giving every deployment a distinct
URL path keeps access logs attributable and prevents any caching layer placed in front of the
endpoint from confusing one deployment's objects with another's.

#### Scenario: An anonymous browser fetch of a presigned URL

- **WHEN** an application mints a presigned URL for an object in its bucket and the URL is
  fetched with no credentials
- **THEN** the object is returned

#### Scenario: A browser uploads directly to the bucket

- **WHEN** a tenant application's page mints a presigned upload URL and a browser uploads to it
  cross-origin, using an unmodified S3 client or a plain `fetch`
- **THEN** the upload succeeds without the tenant having configured anything
- **AND** the response's `ETag` is readable by the page, so multipart uploads work

#### Scenario: Two deployments' presigned URLs are distinguishable

- **WHEN** two storage-enabled deployments each mint a presigned URL for the same object key
- **THEN** the two URLs differ in their path
- **AND** each returns only its own deployment's object

### Requirement: The chart's values schema admits the storage namespace

A chart whose `values.schema.json` sets `additionalProperties: false` SHALL admit the
platform-injected storage values as optional properties, so that a deployment renders both
with and without them.

The values SHALL NOT be marked required: the same chart serves deployments whose product has
not opted in.

#### Scenario: Rendering with storage values

- **WHEN** the chart is rendered with the platform-injected storage values present
- **THEN** schema validation passes and the environment contract is projected

#### Scenario: Rendering without storage values

- **WHEN** the chart is rendered with no storage values
- **THEN** schema validation passes and no object-storage environment variables are projected

### Requirement: The application pod carries no credential it was not issued

A chart that mounts object-storage credentials SHALL NOT also mount a Kubernetes API
ServiceAccount token into the application container, which is issued by default and which the
application has no use for.

This is defense in depth rather than the primary control — the baseline network isolation
already denies a tenant pod egress to the Kubernetes API — but the credential is removed from
the pod's filesystem rather than left present and unreachable.

#### Scenario: No ServiceAccount token in the application container

- **WHEN** the application container of a storage-enabled deployment is inspected
- **THEN** no Kubernetes API ServiceAccount token is mounted into it
