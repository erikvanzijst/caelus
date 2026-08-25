## Purpose
The per-deployment database size allowance, the quota state machine that enforces it,
what each threshold does to a tenant's database, and which of those enforcements are
exact rather than advisory.

## ADDED Requirements

### Requirement: The database allowance comes from the plan and is resolved fail-closed
The allowance SHALL be read from the deployment's subscription plan template
`database_bytes` field. A relational-storage deployment whose plan declares no positive
allowance SHALL fail to provision.

#### Scenario: Allowance is resolved from the plan
- **WHEN** a relational-storage deployment is provisioned
- **THEN** its allowance is the plan template's `database_bytes` value

#### Scenario: Plan declares no allowance
- **WHEN** the plan template declares no positive `database_bytes`
- **THEN** provisioning fails rather than creating an unbounded database

#### Scenario: Allowance is distinct from object storage
- **WHEN** a plan declares both an object-storage allowance and a database allowance
- **THEN** each bounds only its own subsystem

### Requirement: Quota state is measured against logical database size
The system SHALL measure a deployment's usage as the logical size of its PostgreSQL
database and compare it against the plan allowance to derive a quota state of `ok`,
`warned`, `readonly` or `blocked`.

#### Scenario: Usage below the warning threshold
- **WHEN** a database is measured below 80% of its allowance
- **THEN** its quota state is `ok`

#### Scenario: Measurement is recorded
- **WHEN** a deployment's usage is measured
- **THEN** the measured size and the time of measurement are recorded

### Requirement: Thresholds escalate through warning, read-only and refusal
The system SHALL notify at 80% and 90% of the allowance, place the database in
read-only mode at 100%, and refuse the role's login at 150%.

#### Scenario: Warning at 80%
- **WHEN** a database crosses 80% of its allowance
- **THEN** the deployment's owner is notified by email
- **AND** the quota state becomes `warned`

#### Scenario: Warning at 90%
- **WHEN** a database crosses 90% of its allowance
- **THEN** the deployment's owner is notified by email

#### Scenario: Read-only at 100%
- **WHEN** a database reaches its allowance
- **THEN** it is placed in read-only mode
- **AND** the owner is notified that the database is read-only and that the exit is support or a higher plan
- **AND** the quota state becomes `readonly`

#### Scenario: Login refused at 150%
- **WHEN** a database exceeds 150% of its allowance
- **THEN** the deployment role's login is refused
- **AND** existing sessions for that role are terminated
- **AND** the quota state becomes `blocked`

#### Scenario: Repeated warnings are suppressed
- **WHEN** a deployment remains above a threshold across successive measurements
- **THEN** it is not notified again for that threshold

### Requirement: Read-only enforcement is re-asserted on every evaluation
Because a database owner can clear the read-only setting, the system SHALL re-assert it
on every quota evaluation while the deployment remains at or above its allowance.

#### Scenario: A cleared setting is restored
- **WHEN** a tenant clears the read-only setting on their own database and the deployment is next evaluated
- **THEN** read-only is re-applied

#### Scenario: Read-only is lifted when usage falls below the allowance
- **WHEN** a deployment that was read-only is measured below its allowance
- **THEN** read-only is cleared and the quota state returns to `ok` or `warned`

### Requirement: Login refusal is enforced by role state, not by pooler configuration
Refusal of login SHALL be enforced by revoking the deployment role's ability to log in
and terminating that role's existing server connections. It SHALL cause the pooler's
credential lookup to resolve nothing for that role, and SHALL NOT issue, or require,
any pooler administrative command.

#### Scenario: A suspended deployment cannot authenticate
- **WHEN** a suspended deployment's application attempts to connect through the pooler
- **THEN** authentication is refused

#### Scenario: The credential lookup resolves nothing for a suspended role
- **WHEN** the pooler performs its credential lookup for a suspended deployment
- **THEN** no credential is returned

#### Scenario: Suspension holds without any pooler command
- **WHEN** a deployment is suspended and no administrative command is issued to any pooler instance
- **THEN** the deployment is still unable to execute queries

#### Scenario: A client holding an established pooler connection is still cut off
- **WHEN** a deployment is suspended while one of its clients is already connected to the pooler
- **THEN** that client's next query fails because no server connection can be established

#### Scenario: Suspension survives a pooler restart or rescheduling
- **WHEN** a pooler instance restarts while a deployment is suspended
- **THEN** the deployment remains unable to authenticate

#### Scenario: Existing sessions are terminated
- **WHEN** a deployment becomes suspended while sessions are open
- **THEN** those sessions are terminated

#### Scenario: Suspension is lifted
- **WHEN** a suspended deployment is measured below its allowance
- **THEN** its login is restored and it can authenticate again

### Requirement: Quota state is evaluated during reconcile as well as on the schedule
Reconciling a deployment SHALL evaluate and apply its quota state using the same
evaluation as the scheduled sweep, so that an allowance change takes effect without
waiting for the next sweep.

#### Scenario: An increased allowance takes effect immediately
- **WHEN** a read-only deployment's allowance is increased and the deployment is reconciled
- **THEN** read-only is cleared before the workload is deployed

#### Scenario: Reconcile does not grant a write window
- **WHEN** a deployment that is still over its allowance is reconciled
- **THEN** its read-only state is re-asserted rather than cleared

#### Scenario: Reconcile does not notify
- **WHEN** quota state is evaluated during a reconcile
- **THEN** no threshold email is sent

### Requirement: Quota state is not projected onto the deployment record
Quota state SHALL be recorded separately from the deployment's rollout status, and the
deployment status SHALL NOT gain a value representing a quota condition.

#### Scenario: An over-quota deployment is still ready
- **WHEN** a deployment is over its allowance but its rollout is healthy
- **THEN** its deployment status continues to report a healthy rollout

#### Scenario: Quota state is readable
- **WHEN** the platform needs a deployment's quota state
- **THEN** it reads it from the relational-storage record rather than from the deployment status
