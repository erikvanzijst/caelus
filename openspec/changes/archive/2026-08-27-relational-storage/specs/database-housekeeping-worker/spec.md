## Purpose
The long-running process that performs all periodic database housekeeping: measuring
and applying each deployment's quota state, destroying deleted deployments' databases
once their grace period expires, and reclaiming cluster objects that no deployment
record accounts for.

## ADDED Requirements

### Requirement: One process performs all database housekeeping
Database housekeeping SHALL run as a single long-running process, separate from the
reconcile worker and the build worker.

#### Scenario: Housekeeping is independent of reconcile
- **WHEN** the reconcile worker is busy or unavailable
- **THEN** quota measurement and enforcement continue

#### Scenario: All periodic database work shares the process
- **WHEN** the platform performs quota measurement, purging or orphan reclamation
- **THEN** all of it runs in the same housekeeping process

### Requirement: Each periodic task runs on its own interval and is independently guarded
Each task SHALL run on its own schedule, and a failure in one SHALL NOT prevent the
others from running.

#### Scenario: Quota measurement runs frequently
- **WHEN** the process is running
- **THEN** quota state is measured on a configurable interval

#### Scenario: A failing task does not stop the others
- **WHEN** the purge task raises an error
- **THEN** the error is logged and quota measurement continues on its own schedule

#### Scenario: A failed task retries on its next interval
- **WHEN** a task fails
- **THEN** it is attempted again at its next scheduled interval

### Requirement: Purging destroys a deleted deployment's database only after its deadline
The purge task SHALL drop the database and then the role for deployments whose recorded
purge deadline has passed, and SHALL refuse to act on a deployment with no deadline or
a deadline in the future.

#### Scenario: A deployment past its deadline is purged
- **WHEN** a deleted deployment's purge deadline has passed
- **THEN** its database is dropped and then its role is dropped

#### Scenario: A deployment within its grace period is untouched
- **WHEN** a deleted deployment's purge deadline has not yet passed
- **THEN** its database and data remain

#### Scenario: A missing deadline is never purged
- **WHEN** a record carries no purge deadline
- **THEN** the purge task takes no destructive action on it

#### Scenario: Connected sessions do not block the purge
- **WHEN** sessions are connected to a database that is due for purging
- **THEN** the drop still succeeds

#### Scenario: Purging is bounded per run
- **WHEN** more deployments are due for purging than the configured per-run maximum
- **THEN** the task purges no more than that maximum in one run

#### Scenario: Every destruction is recorded
- **WHEN** a database is dropped
- **THEN** the event is logged with the deployment it belonged to

### Requirement: Orphan reclamation covers both databases and roles
The orphan task SHALL identify tenant databases and roles on the cluster that no
relational-storage record accounts for, so that objects left behind by an interrupted
provision are found.

#### Scenario: A database without a record is identified
- **WHEN** a tenant database exists that no record accounts for
- **THEN** the orphan task identifies it

#### Scenario: A role without a database is identified
- **WHEN** a role was created but its database never was
- **THEN** the orphan task identifies the role

#### Scenario: Provisioned deployments are not treated as orphans
- **WHEN** a database and role match an existing record
- **THEN** they are not identified as orphans

### Requirement: The housekeeping process holds a privileged connection never exposed to tenants
The process SHALL connect to the tenant cluster with an administrative credential that
is never placed in any tenant's environment, values or Secret.

#### Scenario: The administrative credential stays platform-side
- **WHEN** a tenant inspects its own environment, Secret or rendered values
- **THEN** no administrative credential is present
