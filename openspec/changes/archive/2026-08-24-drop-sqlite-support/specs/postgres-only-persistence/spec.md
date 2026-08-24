## Purpose

Establishes PostgreSQL as the only database Caelus supports, so that every
constraint, locking primitive, and index predicate the application depends on
behaves identically in development, test, and production.

## ADDED Requirements

### Requirement: PostgreSQL is the only supported database
The system SHALL support PostgreSQL as its only database backend. The
application MUST NOT carry alternate code paths, connection arguments, or
schema declarations selected by database dialect.

#### Scenario: Application connects to its database
- **WHEN** the API, the `caelus` CLI, the reconcile worker, or the build worker
  opens a database connection
- **THEN** it SHALL do so without inspecting the dialect of the configured
  database URL
- **AND** no pooling or connect-argument choice SHALL depend on that dialect

#### Scenario: A non-PostgreSQL database URL is configured
- **WHEN** `CAELUS_DATABASE_URL` names a database that is not PostgreSQL
- **THEN** the system SHALL NOT adapt its behavior to that database
- **AND** the resulting failure SHALL surface from the driver or the schema
  rather than being silently accommodated

### Requirement: Queue claiming uses row-level locking unconditionally
Claiming a reconcile job and claiming a build SHALL each use PostgreSQL
row-level locking that skips rows locked by other workers, with no fallback
strategy for other dialects.

#### Scenario: Concurrent workers claim from the reconcile queue
- **WHEN** multiple workers claim from the reconcile queue at the same time
- **THEN** each queued job SHALL be claimed by at most one worker
- **AND** the claim SHALL be performed by the row-locking path, with no
  dialect check preceding it

#### Scenario: Concurrent workers claim builds
- **WHEN** multiple build workers claim pending builds at the same time
- **THEN** each pending build SHALL be claimed by at most one worker
- **AND** build identifiers SHALL be handled as native UUID values, without
  hexadecimal-string conversion

### Requirement: Partial index predicates are declared for PostgreSQL only
Partial index declarations on models SHALL carry a PostgreSQL predicate and
SHALL NOT carry predicates for any other dialect.

#### Scenario: A model declares a partial unique index
- **WHEN** a model table declares a partial unique index
- **THEN** the declaration SHALL specify `postgresql_where`
- **AND** it SHALL NOT specify a predicate keyword for any other dialect

#### Scenario: Historical migration revisions are inspected
- **WHEN** an already-applied Alembic revision declares a partial index using
  another dialect's predicate keyword
- **THEN** that revision SHALL be left unmodified, because the keyword is inert
  against PostgreSQL and editing applied revisions is unsafe

### Requirement: Migrations always take the advisory lock
Applying migrations SHALL acquire the migration advisory lock unconditionally,
so that concurrent `alembic upgrade` runs serialize rather than collide.

#### Scenario: Two upgrade runs start simultaneously
- **WHEN** two `alembic upgrade head` processes start against the same database
  at the same time
- **THEN** both SHALL succeed
- **AND** the second SHALL wait on the advisory lock held by the first
- **AND** no dialect condition SHALL guard the lock acquisition
