# cli-releases Specification

## Purpose
Listing what the current project has actually rolled out: the deployment's
releases, in the platform's order, with the one serving traffic marked. Where
the build history answers "what has this account built", this answers "what has
this project deployed, and how did each attempt end".

## Requirements

### Requirement: The listing is the current project's deployment

Unlike the build history, a release belongs to a deployment rather than to an
account, so the client SHALL list the releases of the deployment recorded in the
current project and SHALL NOT offer an account-wide listing. There is no
account-wide release listing to fall back to, and inventing one would mean
merging the histories of unrelated deployments into a single ordering.

Where no project file is found, or the project records no deployment, the client
SHALL refuse as a usage error naming what is missing and what would produce it,
rather than printing an empty table — an empty table would read as "this
deployment has never rolled out", which is a different and untrue statement.

Where the project records a deployment on a different environment than the one
targeted, the client SHALL refuse and name both environments, for the same
reason the teardown does: a listing that silently read the wrong environment
would report another deployment's history as this one's.

#### Scenario: Releases of the project's deployment are listed

- **WHEN** the command runs in a project that records a deployment
- **THEN** that deployment's releases are listed

#### Scenario: No project file

- **WHEN** the command runs where no project file exists
- **THEN** it refuses as a usage error and says how a project is created

#### Scenario: A project that has never deployed

- **WHEN** the command runs in a project recording no deployment
- **THEN** it refuses as a usage error and says that deploying creates one, rather than printing an empty table

#### Scenario: A project belonging to another environment

- **WHEN** the project records a deployment on one environment and the command targets another
- **THEN** it refuses and names both environments

### Requirement: Releases are presented in the platform's order

The client SHALL present the releases in the order the endpoint returns them —
most recent first — and SHALL NOT reorder them. The platform orders by release
number, which is the ledger's own ordering key; re-deriving that order in the
client would reproduce an answer already given and would misplace any row whose
number or timestamp could not be read.

#### Scenario: The platform's order is preserved

- **WHEN** the platform returns releases most recent first
- **THEN** they are presented in that order

### Requirement: Each release reports its number, outcome, timing and what it shipped

Every listed release SHALL report its number, its status, when it was requested,
how long the rollout took, and the build it shipped where it names one.

The rollout's duration SHALL be measured from when work began rather than from
when the release was created: the wait for a worker is queueing, and counting it
would report a fast rollout as a slow one whenever the queue was busy. A release
that has not started SHALL report no duration, and one still in flight SHALL
report the time elapsed so far. This is the same measurement the build history
makes, for the same reason.

Timestamps SHALL be presented in the reader's own timezone. A release naming no
build SHALL be shown as having none rather than being omitted — most products
build nothing, and omitting those rows would hide most of the history for them.

A release whose rollout failed SHALL be identifiable as failed from its row, and
its recorded error SHALL be available to the reader.

#### Scenario: A queued release reports no duration

- **WHEN** a release has been created and no rollout has begun
- **THEN** it is listed as queued with no duration

#### Scenario: An in-flight release reports elapsed time

- **WHEN** a rollout has begun and not finished
- **THEN** the time elapsed since it began is reported

#### Scenario: A failed release is legible as failed

- **WHEN** a rollout failed
- **THEN** its row reports the failed status and the reader can see the recorded error

#### Scenario: A release for a product that builds nothing

- **WHEN** a release names no build
- **THEN** it is listed with no build rather than omitted

### Requirement: The release the deployment is running is marked

The client SHALL mark the release the deployment is currently running, taken
from what the deployment reports as applied rather than derived from the listing.
The desired release SHALL NOT be read as the running one: after a failed
rollout the two differ, and marking the desired one would report a failed
release as the one serving traffic.

Every way of not knowing SHALL yield an unmarked listing rather than a failure —
a deployment that has never successfully rolled out has nothing applied, and
that is a listing with no mark rather than an error. The meaning of the mark
SHALL be stated whenever one is shown.

#### Scenario: The applied release is marked

- **WHEN** the deployment reports an applied release present in the listing
- **THEN** that release is marked and no other is

#### Scenario: A failed rollout does not move the mark

- **WHEN** the newest release failed and an older one is still applied
- **THEN** the older release carries the mark

#### Scenario: A deployment that has never rolled out successfully

- **WHEN** the deployment reports no applied release
- **THEN** the releases are listed with nothing marked

### Requirement: The listing is bounded by default and says what it withheld

The client SHALL show a bounded number of the most recent releases by default,
SHALL allow that bound to be changed or lifted, and SHALL report how many
releases were withheld whenever it shows fewer than the deployment has. A bound
that hides rows silently would misrepresent the deployment's history.

A bound that could show nothing SHALL be refused as a usage error.

#### Scenario: A truncated listing says how much it withheld

- **WHEN** the deployment has more releases than the listing shows
- **THEN** the client reports how many of how many were shown, and how to see them all

#### Scenario: The bound can be lifted

- **WHEN** the reader asks for every release
- **THEN** all releases are listed and nothing is reported as withheld

#### Scenario: A bound that shows nothing is refused

- **WHEN** the reader asks for a non-positive number of releases
- **THEN** the command refuses as a usage error

### Requirement: The table is the result and everything else is a diagnostic

The client SHALL write the table to standard output, and SHALL write the
explanation of the mark, the withheld-release count, and every other remark to
standard error, so that a redirected listing carries rows and nothing else.
Suppressing diagnostics SHALL leave the table intact.

#### Scenario: A redirected listing carries only rows

- **WHEN** the listing is redirected
- **THEN** standard output carries the table
- **AND** the legend and counts do not appear in it

#### Scenario: Suppressing diagnostics keeps the table

- **WHEN** the listing runs with diagnostics suppressed
- **THEN** the table is still written to standard output
