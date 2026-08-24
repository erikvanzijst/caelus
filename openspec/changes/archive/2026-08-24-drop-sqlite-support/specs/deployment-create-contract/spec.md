## ADDED Requirements

### Requirement: The stored hostname column permits no value
The `deployment.hostname` column SHALL permit NULL. A deployment whose desired
template declares no hostname-titled field is a valid deployment, and storing
it MUST NOT be rejected by the database.

This closes a contradiction between the schema and the requirement "Create and
update services derive hostname from template schema and user values", whose
scenario "Template schema has no hostname-titled field" already requires the
service to persist `DeploymentORM.hostname` as `null`.

#### Scenario: Creating a deployment from a template with no hostname field
- **WHEN** a deployment is created from a desired template whose schema
  contains no field titled `hostname`
- **THEN** the deployment SHALL be persisted with `hostname` set to `null`
- **AND** the database SHALL accept the insert

#### Scenario: Updating a deployment onto a template with no hostname field
- **WHEN** a deployment is updated so that its re-derived hostname is `null`
- **THEN** the deployment SHALL be persisted with `hostname` set to `null`
- **AND** the database SHALL accept the update

#### Scenario: A deployment that does have a hostname
- **WHEN** a deployment is created from a template that does declare a
  hostname-titled field
- **THEN** the derived hostname SHALL be persisted as before, and the relaxed
  constraint SHALL change nothing about validation or uniqueness
