# deployment-release-api Specification

## Purpose
The read surface of the release ledger: asking a deployment what rollouts it has
had, in what order, with what outcome, and what each one shipped. The ledger
records every rollout; this is how a caller gets at the ones that are not the
one currently running.

## Requirements

### Requirement: A deployment's releases can be listed

The system SHALL provide an endpoint listing the releases of one deployment,
addressed under the deployment's owner. Releases of other deployments MUST NOT
appear.

The listing SHALL be ordered by release number, **highest first**, so the most
recent rollout is the first row. Number is the ordering key rather than a
timestamp, for the reason the ledger already gives: ordering must not depend on
clock resolution.

Every release SHALL be listed whatever its outcome — queued, in flight,
abandoned, failed or succeeded. A listing that showed only successful rollouts
would omit precisely the ones a caller asks about.

A deployment that has releases always has at least one, because a deployment is
created together with its first release; there is no empty-listing case for a
deployment that exists.

#### Scenario: Releases are listed most recent first

- **WHEN** the releases of a deployment with three rollouts are listed
- **THEN** three releases are returned, numbered 3, 2, 1 in that order

#### Scenario: Failed and queued releases are listed too

- **WHEN** a deployment has a failed rollout and a rollout that has not yet started
- **THEN** both appear in the listing alongside the successful ones

#### Scenario: Another deployment's releases do not appear

- **WHEN** a user with two deployments lists the releases of one of them
- **THEN** only that deployment's releases are returned

### Requirement: A release is addressed by its per-deployment number

The system SHALL provide an endpoint returning a single release of a deployment,
identified by the release's **per-deployment number** and not by its internal
identifier.

The ledger already requires that the number is the identifier presented to users
and accepted from them, and that the internal `uuid4` remains the unguessable
value stamped onto pods. Accepting the number here is what makes a release
something a person can read off a listing and ask about directly.

A number that no release of that deployment carries SHALL be reported as not
found, as SHALL a number belonging to a release of a different deployment.

#### Scenario: A release is read by its number

- **WHEN** release 2 of a deployment is requested
- **THEN** the release numbered 2 for that deployment is returned

#### Scenario: A number the deployment has never reached

- **WHEN** release 9 of a deployment that has had three rollouts is requested
- **THEN** the request is reported as not found

#### Scenario: A number is scoped to its own deployment

- **WHEN** release 1 is requested for each of two different deployments
- **THEN** each request returns that deployment's own first release

### Requirement: A release reports its identity, intent, outcome and timing

Every release — listed or read singly — SHALL report its number, the deployment
it belongs to, the template it deploys, the build it names if any, the user
values it was requested with, when it was created, when work on it began and
ended, any error recorded against it, and its **derived status**.

The status SHALL be derived at read time rather than stored, so that a rollout
whose worker died is reported as abandoned once its lease has elapsed without
anything having to write that transition.

The status values SHALL be those the ledger defines: queued, in flight,
abandoned, failed, succeeded.

#### Scenario: A queued release reports no timing

- **WHEN** a release that has not started is read
- **THEN** its status is queued, and it reports no start, no end and no error

#### Scenario: A failed release reports its error

- **WHEN** a release whose rollout failed is read
- **THEN** its status is failed and the recorded error is returned with it

#### Scenario: A release whose worker died is reported as abandoned

- **WHEN** a release that started longer ago than the reconcile lease is read, and it has not ended
- **THEN** its status is abandoned, without any component having written that transition

### Requirement: A release carries the build it shipped

Both the listing and the single-release read SHALL include the referenced
**build object**, not merely its identifier, so that what a rollout shipped —
its status, its image, its timings — is answered by the request that asked about
the rollout. A reader comparing two rollouts is comparing what they shipped, and
an identifier alone makes that a second request per row.

A release naming no build SHALL report none rather than being refused or having
the field omitted: builds exist only for products that deploy tenant-supplied
code, so a release with no build is a curated product, not an incomplete record.
Such a release SHALL still appear in the listing — it MUST NOT be dropped for
having no build to inline.

Including the build SHALL NOT cost a request or a query per release. The number
of queries a listing performs SHALL NOT grow with the number of releases it
returns.

#### Scenario: The build is returned with a single release

- **WHEN** a release naming a build is read singly
- **THEN** the response carries the build's own record, including the image it produced

#### Scenario: The build is returned with every listed release

- **WHEN** a deployment's releases are listed
- **THEN** each release that names a build carries that build's record, not merely its identifier

#### Scenario: A release with no build

- **WHEN** a release naming no build is read, singly or in a listing
- **THEN** it is returned with no build rather than an error, and it is not omitted from the listing

#### Scenario: Listing many releases does not multiply queries

- **WHEN** a deployment with many releases, each naming a build, is listed
- **THEN** the number of queries performed does not grow with the number of releases

### Requirement: Release reads are scoped to the deployment's owner

Both endpoints SHALL be scoped to the owner of the deployment named in the
request path. A caller MAY read the releases of their own deployments;
administrators MAY read any. A caller naming another account SHALL be refused.

A deployment belonging to another user, and one that does not exist, SHALL be
indistinguishable, so the endpoints cannot be used to probe for other users'
deployments. A deployment that has been deleted SHALL be treated as one that
does not exist, matching what a deployment read already answers.

#### Scenario: Another account's releases are refused

- **WHEN** a non-administrator requests the releases of a deployment under another user's account
- **THEN** the request is refused as forbidden

#### Scenario: Another user's deployment is not found

- **WHEN** a caller requests releases for a deployment identifier that is not theirs, under their own account
- **THEN** the response is indistinguishable from one for a deployment that does not exist

#### Scenario: An administrator reads any deployment's releases

- **WHEN** an administrator requests the releases of another user's deployment
- **THEN** the releases are returned

#### Scenario: A deleted deployment has no releases to read

- **WHEN** the releases of a deleted deployment are requested
- **THEN** the response is not found
