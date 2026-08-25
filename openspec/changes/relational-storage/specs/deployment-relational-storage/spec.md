## Purpose
How a PostgreSQL database and a dedicated login role are provisioned, isolated,
credentialed and reclaimed for an individual deployment on the shared tenant cluster —
and what the isolation between two deployments' databases actually rests on, given that
PostgreSQL grants every role access to every database by default.

## ADDED Requirements

### Requirement: Relational storage is a product-level opt-in
The system SHALL provision relational storage only for deployments whose product
template declares it, and SHALL read that declaration from the template's system
values, never from user values.

#### Scenario: Product opts in
- **WHEN** a deployment's product template declares relational storage enabled in its system values
- **THEN** the reconciler provisions a database and role for that deployment

#### Scenario: Product has not opted in
- **WHEN** a deployment's product template does not declare relational storage
- **THEN** no database, role or credentials are created
- **AND** the deployment's rendered values carry no database block at all

#### Scenario: Tenant attempts to opt in
- **WHEN** a tenant supplies a relational-storage flag through user values
- **THEN** the flag SHALL NOT enable provisioning

### Requirement: Database and role are named from the deployment identifier
The database and the login role SHALL share one name, derived from the deployment's
identifier with any characters invalid in an unquoted PostgreSQL identifier removed.
The name SHALL be a valid unquoted identifier within PostgreSQL's 63-byte limit.

#### Scenario: Name is derived and stable
- **WHEN** a database is provisioned for a deployment
- **THEN** the database name and the role name are the same string
- **AND** the name is derived from the deployment identifier
- **AND** the name requires no quoting in SQL statements

#### Scenario: Name survives reconciliation
- **WHEN** a deployment is reconciled repeatedly
- **THEN** the database and role names do not change

### Requirement: The deployment role owns its database and holds no cluster privileges
The role SHALL be created as the owner of its database, and SHALL be created without
the superuser, createdb, createrole, replication and bypassrls attributes.

#### Scenario: Role owns its own database
- **WHEN** a database is provisioned
- **THEN** the deployment role is its owner
- **AND** the role can create schemas, tables and trusted extensions within it

#### Scenario: Role cannot provision around its quota
- **WHEN** the deployment role attempts to create another database
- **THEN** PostgreSQL denies the operation

#### Scenario: Role cannot alter its own attributes
- **WHEN** the deployment role attempts to alter its own login attribute
- **THEN** PostgreSQL denies the operation

### Requirement: Cross-tenant access is revoked explicitly
Because PostgreSQL grants CONNECT to PUBLIC on every new database, provisioning SHALL
revoke CONNECT from PUBLIC on each tenant database, and the tenant cluster's
maintenance databases SHALL have the same revocation applied.

#### Scenario: One tenant cannot connect to another's database
- **WHEN** deployment A's role attempts to connect to deployment B's database
- **THEN** the connection is refused for lack of CONNECT privilege

#### Scenario: A tenant cannot connect to a maintenance database
- **WHEN** a deployment role attempts to connect to the tenant cluster's default or template databases
- **THEN** the connection is refused

#### Scenario: The owner is unaffected
- **WHEN** a deployment role connects to its own database after the revocation
- **THEN** the connection succeeds

#### Scenario: A tenant cannot exhaust another tenant's connection allowance
- **WHEN** deployment A opens connections against deployment B's database
- **THEN** those connections are refused before they can consume B's allowance

### Requirement: Session limits are applied to the deployment role
Provisioning SHALL apply a temporary-file limit, a statement timeout and an
idle-in-transaction timeout to the deployment role, and SHALL re-apply them on every
reconcile.

#### Scenario: Temporary file consumption is bounded
- **WHEN** a tenant session generates temporary files beyond the configured limit
- **THEN** PostgreSQL aborts the statement
- **AND** the tenant SHALL NOT be able to raise the limit

#### Scenario: Timeouts are re-applied
- **WHEN** a tenant clears a role-level timeout and the deployment is reconciled
- **THEN** the configured value is restored

### Requirement: The password is platform-held and re-asserted on every reconcile
Because a PostgreSQL password cannot be read back, the system SHALL generate it, store
it encrypted under the platform's rotatable keyring, and re-assert it on the role
during every reconcile. The encrypted value SHALL be persisted before the password is
applied to the role.

#### Scenario: Password is stored before being applied
- **WHEN** provisioning generates a password
- **THEN** the encrypted password is persisted before the role is altered

#### Scenario: An interrupted provision self-heals
- **WHEN** provisioning is interrupted after storing the password but before applying it
- **THEN** the next reconcile applies the stored password and the credential works

#### Scenario: Tenant-side rotation does not persist
- **WHEN** a tenant changes their own database password and the deployment is reconciled
- **THEN** the platform's stored password is re-asserted
- **AND** the credential in the pod's environment continues to work

### Requirement: Provisioning is idempotent and each step independently verified
Each provisioning step SHALL read before it writes and SHALL be verified independently
of the others, so that a run interrupted between any two steps is completed by the next
run rather than being treated as finished.

#### Scenario: Re-running provisioning changes nothing
- **WHEN** a deployment with an existing database and role is reconciled
- **THEN** provisioning completes without creating duplicates and without rotating the credential

#### Scenario: A partially provisioned deployment is completed
- **WHEN** a role exists but its database does not
- **THEN** the next reconcile creates the database rather than concluding from the role that provisioning is done

### Requirement: Provisioning fails closed
If the tenant cluster cannot be reached or the deployment's plan declares no database
allowance, the reconcile SHALL fail rather than deploying a pod without a database.

#### Scenario: Tenant cluster is unreachable
- **WHEN** the tenant cluster cannot be reached during a reconcile of a relational-storage deployment
- **THEN** the reconcile fails and no workload is deployed

#### Scenario: Plan declares no allowance
- **WHEN** a relational-storage deployment's plan declares no database allowance
- **THEN** provisioning fails rather than creating an unbounded database

### Requirement: Deletion revokes access immediately and defers destruction
On deployment deletion the system SHALL revoke the role's ability to log in and record
a purge deadline, and SHALL NOT drop the database or the role during the delete
reconcile.

#### Scenario: Access is revoked at deletion
- **WHEN** a deployment with relational storage is deleted
- **THEN** its role can no longer log in
- **AND** its database and data still exist

#### Scenario: Purge deadline is recorded
- **WHEN** a deployment is deleted
- **THEN** a purge deadline is recorded using the platform's configured grace period

#### Scenario: Nothing irreversible runs on the delete path
- **WHEN** the delete reconcile runs
- **THEN** no database or role is dropped
- **AND** the delete reconcile can be retried safely

#### Scenario: Deployment never had a database
- **WHEN** a deployment without relational storage is deleted
- **THEN** deletion completes without error
