# cross-database-partial-index-parity Specification

## Purpose
Governs the partial unique indexes that enforce "at most one active row" rules
— one active deployment per uniqueness key, and the deliberate absence of such
a rule on product template versions — along with how the migrations that change
them are produced.

The capability was named when these predicates had to be declared twice, once
per dialect. PostgreSQL is now the only backend, and the parity requirement was
removed by the `drop-sqlite-support` change; predicate declaration itself now
lives in `postgres-only-persistence`. The name is retained so the requirement
history stays traceable.

## Requirements

### Requirement: Deployment active uniqueness MUST be status-based
The system MUST enforce deployment active uniqueness using `status` predicates, and `uq_deployment_active` MUST use a status-based partial predicate rather than `deleted_at`.

#### Scenario: Creating a deployment while an active one exists
- **WHEN** a user creates a deployment that matches a uniqueness key and an existing deployment is in an active status
- **THEN** the database SHALL reject the insert/update through the deployment active partial unique index

#### Scenario: Existing deployment is not active
- **WHEN** a matching deployment exists but its status is outside the active-status set
- **THEN** the database SHALL allow the insert/update because the inactive row is outside the partial index predicate

### Requirement: Product template versions MUST allow duplicate templates
The system MUST NOT enforce uniqueness via the `uq_producttemplate_active` partial unique index on `ProductTemplateVersionORM`.

#### Scenario: Creating duplicate template versions
- **WHEN** two template version rows are created with identical template content for the same product scope
- **THEN** both rows SHALL persist without uniqueness rejection from `uq_producttemplate_active`

### Requirement: Migration MUST include only intended partial index changes
The migration generated for this change MUST be produced from Alembic autogenerate and then manually curated to include only the targeted partial-index updates.

#### Scenario: Reviewing migration contents
- **WHEN** the new Alembic revision is finalized
- **THEN** it SHALL contain only the index drop/create/remove operations required for this change and exclude unrelated schema modifications
