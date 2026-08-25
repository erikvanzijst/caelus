## Purpose
The shared PostgreSQL server and connection pooler that hold every `custom` deployment's
database: how they are versioned, isolated from the control plane, authenticated,
bounded in resources, and what capacity limits they operate under on a single-node
cluster whose storage class enforces nothing.

## ADDED Requirements

### Requirement: The tenant cluster is separate from the control-plane database
Tenant databases SHALL be hosted on a PostgreSQL instance separate from the one holding
platform tables, and each Terraform workspace SHALL have its own tenant cluster.

#### Scenario: Control plane is unaffected by tenant load
- **WHEN** a tenant saturates the tenant cluster
- **THEN** the platform's own database is unaffected

#### Scenario: Environments do not share a cluster
- **WHEN** a deployment is provisioned in the development environment
- **THEN** its database is created on that environment's tenant cluster and not on production's

### Requirement: Applications reach the cluster only through the pooler
Tenant workloads SHALL connect through the pooler, and SHALL NOT be able to reach the
PostgreSQL server directly.

#### Scenario: Pooler is reachable
- **WHEN** a tenant pod connects to the pooler endpoint
- **THEN** the connection is permitted

#### Scenario: Direct PostgreSQL access is refused
- **WHEN** a tenant pod attempts to connect to the PostgreSQL server directly
- **THEN** the connection is denied by network policy

### Requirement: The pooler uses transaction pooling with prepared-statement support
The pooler SHALL use transaction pooling and SHALL support protocol-level prepared
statements, so that common drivers and ORMs work with their default settings.

#### Scenario: A default driver connects successfully
- **WHEN** an application connects using a driver that issues prepared statements by default
- **THEN** its queries succeed without the application disabling prepared statements

#### Scenario: Many clients share fewer server connections
- **WHEN** more client connections are open than server connections
- **THEN** clients are multiplexed over the server pool

### Requirement: Pooler authentication resolves against a platform-owned database
The pooler's authentication lookup SHALL be pinned to a database that no tenant can
reach, so that no tenant can influence how credentials are resolved.

#### Scenario: Lookup does not occur in a tenant database
- **WHEN** a tenant connects to their own database through the pooler
- **THEN** the credential lookup is performed against the platform-owned database, not the tenant's

#### Scenario: A tenant cannot define the lookup
- **WHEN** a tenant creates objects in their own database matching the lookup's names
- **THEN** authentication behavior is unaffected

### Requirement: Provisioning a deployment requires no pooler restart or reconfiguration
Adding or removing a deployment SHALL NOT require restarting the pooler, and SHALL NOT
interrupt other deployments' connections.

#### Scenario: A new deployment is provisioned
- **WHEN** a database and role are created for a new deployment
- **THEN** that deployment can connect through the pooler without any pooler restart

#### Scenario: Existing deployments are undisturbed
- **WHEN** a deployment is provisioned or removed
- **THEN** other deployments' connections are not interrupted

### Requirement: The pooler runs more than one instance behind a stable endpoint
The pooler SHALL run at least two instances behind one stable in-cluster endpoint, so
that the loss of a single instance does not disconnect the whole fleet.

#### Scenario: One instance is lost
- **WHEN** one pooler instance is drained or restarted
- **THEN** new connections are served by a remaining instance

#### Scenario: Client-side limits are understood as per-instance
- **WHEN** a client connection limit is configured on the pooler
- **THEN** it applies per instance, and the platform's effective limit is that value multiplied by the instance count

### Requirement: A single global connection limit applies to all deployments
The pooler SHALL apply one connection limit shared by every deployment rather than a
per-plan limit.

#### Scenario: No per-plan differentiation
- **WHEN** deployments on different plans connect
- **THEN** the same connection limit applies to each

### Requirement: PostgreSQL and the pooler run under explicit resource bounds
Both SHALL declare CPU and memory requests and limits, and PostgreSQL's own memory
configuration SHALL be set below its container memory limit so that the container is
not terminated for exceeding it.

#### Scenario: Memory ceiling sits below the container limit
- **WHEN** PostgreSQL runs at its configured maximum memory usage
- **THEN** it remains below its container memory limit

#### Scenario: Resource bounds are declared
- **WHEN** the tenant cluster is deployed
- **THEN** PostgreSQL and each pooler instance declare CPU and memory requests and limits

### Requirement: Physical storage safety does not rely on the volume's declared size
Because the cluster's storage class enforces no size limit and cannot expand a volume,
the platform SHALL treat the tenant cluster's storage budget as self-imposed, monitor
the node's actual free disk, and alert an operator when the reserve is crossed.

#### Scenario: The reserve is crossed
- **WHEN** the node's free disk falls below the configured reserve
- **THEN** an operator is alerted

#### Scenario: No automatic global degradation
- **WHEN** the reserve is crossed
- **THEN** the platform does not automatically place unrelated deployments in read-only mode or suspend them

#### Scenario: Logical quotas are not the volume's protection
- **WHEN** the sum of all deployments' allowances exceeds the storage budget
- **THEN** the platform still operates, and physical safety rests on monitoring rather than on the quota sum

### Requirement: Tenants may install only trusted extensions
A deployment role SHALL be able to install PostgreSQL's trusted extensions in its own
database, and SHALL NOT be able to install untrusted ones.

#### Scenario: A trusted extension is installable
- **WHEN** a deployment role creates a trusted extension in its own database
- **THEN** the extension is created

#### Scenario: An untrusted extension is refused
- **WHEN** a deployment role creates an untrusted extension
- **THEN** PostgreSQL refuses the operation
