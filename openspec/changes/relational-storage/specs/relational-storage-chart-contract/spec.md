## Purpose
The contract between the platform and a tenant's container image: how database
credentials reach a pod, what environment variables an application may rely on, and the
guarantee that an unmodified PostgreSQL client or ORM connects against them without any
configuration.

## ADDED Requirements

### Requirement: Credentials reach the pod through a Kubernetes Secret
The database password SHALL be delivered to the pod through a Kubernetes Secret in the
deployment's own namespace, and SHALL NOT appear in Helm values.

#### Scenario: Secret is written before the workload starts
- **WHEN** a relational-storage deployment is reconciled
- **THEN** the credentials Secret exists in the deployment's namespace before Helm runs

#### Scenario: Password never enters values
- **WHEN** the merged Helm values for a deployment are rendered or logged
- **THEN** they contain no database password

#### Scenario: Secret is updated in place
- **WHEN** a deployment is reconciled repeatedly
- **THEN** the same Secret is updated rather than a new one created per reconcile

### Requirement: The pod environment carries a connection URL and discrete parameters
The Secret SHALL provide a `DATABASE_URL` connection string and the discrete
`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `PGDATABASE` variables.

#### Scenario: An ORM connects with no configuration
- **WHEN** an application reads `DATABASE_URL` using a standard PostgreSQL ORM or driver
- **THEN** it connects to the deployment's own database

#### Scenario: A libpq client connects with no configuration
- **WHEN** an application or tool relies on the standard `PG*` environment variables
- **THEN** it connects to the deployment's own database without further arguments

#### Scenario: The URL addresses the pooler
- **WHEN** the connection variables are read
- **THEN** they address the pooler, not the PostgreSQL server directly

### Requirement: Helm values carry database references only
The reconciler SHALL project the host, port, database name, role name and the
credentials Secret's name into a platform-owned values namespace, and SHALL emit no
database block for a product that has not opted in.

#### Scenario: References are projected
- **WHEN** a relational-storage deployment is reconciled
- **THEN** the rendered values carry the database host, port, name, user and the Secret's name

#### Scenario: Product has not opted in
- **WHEN** a deployment whose product has not opted in is reconciled
- **THEN** the rendered values contain no database block

#### Scenario: A tenant cannot claim another deployment's database
- **WHEN** a tenant supplies database values through user values
- **THEN** the platform's values take precedence and the tenant's are not used

### Requirement: The chart declares both the opt-in flag and the injected references
The product chart's values schema SHALL declare the product-level opt-in flag and the
platform-injected database references as distinct inputs, so that a chart with a closed
values schema accepts both.

#### Scenario: Chart accepts the opt-in flag
- **WHEN** the catalog sets the relational-storage opt-in flag as a system value
- **THEN** the chart's values schema accepts it and the rollout succeeds

#### Scenario: Chart accepts injected references
- **WHEN** the reconciler injects the per-deployment database references
- **THEN** the chart's values schema accepts them

#### Scenario: The two are distinguishable
- **WHEN** a reader inspects the chart's values
- **THEN** the static product declaration and the per-deployment runtime facts are separate keys
