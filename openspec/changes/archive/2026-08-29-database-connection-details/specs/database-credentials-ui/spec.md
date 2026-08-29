## Purpose

Deployment owners work through the web UI, so a database they cannot see there is a
database they cannot reason about. This capability adds a panel to the deployment view
presenting which database and role the deployment owns, the password that owns it, and the
database's health against its allowance. It follows the existing SFTP panel's shape: its
own component, shown only when the deployment actually has a database, with a secret masked
by default.

The panel shows no address and no connection URL. The pooler is reachable only from inside
the cluster, and a browser will never have a tunnel to it, so an address here could only
ever be a wrong answer to "how do I connect" — which the panel answers instead by saying
where the database can be reached from. What it does show is the part that stays true
however a connection is eventually made.

## ADDED Requirements

### Requirement: The deployment view shows a database panel when a database exists
The deployment detail view MUST present a database panel for deployments that have relational storage, showing the database name, the role name and the password, with the password masked by default and revealable, and a copy affordance for each field.

The panel MUST NOT show the pooler host or port, and MUST NOT compose or offer a connection URL. The address is in-cluster and the reader's browser has no route to it; presenting it as a field to copy offers a connection that cannot be made. The database name, role and password are shown because they are the deployment's own, are visible nowhere else, and remain correct whatever route to the database eventually exists.

The panel MUST be its own component under the components directory, not inlined into a page-level component, matching the project's standing rule and the existing SFTP panel.

#### Scenario: Owner views the details
- **WHEN** the owner opens the detail view of a deployment whose database is provisioned
- **THEN** the panel shows the database name, the role name and a masked password
- **AND** the password can be revealed and each field copied

#### Scenario: No address or URL is offered
- **WHEN** the panel renders for a provisioned database
- **THEN** it shows neither the pooler host nor the pooler port, and offers no connection URL to copy

#### Scenario: Panel is a dedicated component
- **WHEN** the deployment view renders the panel
- **THEN** it composes a dedicated component rather than defining the panel inline

### Requirement: The panel is absent when the product has no relational storage
When the platform reports that a deployment's product offers no relational storage, the UI MUST NOT render the panel or any placeholder implying a database exists.

#### Scenario: Product without relational storage
- **WHEN** the owner opens the detail view of a deployment whose product offers no database
- **THEN** no database panel is shown

### Requirement: A transitional deployment is handled by the existing settled pattern
The panel MUST take its cue from the deployment's own status rather than treating a temporarily absent database as a state of its own, and MUST re-request the details when a transitional deployment settles — the pattern the deployment view already uses for the SFTP panel.

A database is provisioned before its deployment reaches the ready state, so an absent database on a settled deployment means the product has none, while an absent database on a transitional one means the deployment is still being worked on and is already presented as such.

#### Scenario: Details appear once the deployment settles
- **WHEN** a deployment that was transitional becomes settled
- **THEN** the panel requests the details again and renders them without the reader reloading the page

#### Scenario: No separate provisioning presentation
- **WHEN** a deployment is transitional
- **THEN** the panel does not introduce a database-specific "being prepared" state alongside the deployment's own status display

### Requirement: The panel states how the database is reached
The panel MUST state that the database is reachable from the deployment's own application and not from the reader's machine, and MUST NOT present the details it shows as credentials to paste into a local client and connect with.

Withholding the address removes the wrong answer; it does not supply the right one. A reader looking at a role and a password will ask how to use them, and the panel must answer rather than leave the omission to be read as a gap.

#### Scenario: Reader is not misled into connecting
- **WHEN** the panel renders the database's details
- **THEN** it states that the database is reachable from the running application rather than from the reader's machine

#### Scenario: Wording does not promise a future feature as present
- **WHEN** the panel explains the limitation
- **THEN** it describes the current state without asserting that a local connection is available

### Requirement: Quota state and usage are shown, and a degraded database is prominent
The panel MUST show how much of its allowance the database is using, and when that was last measured, so a stale figure is not read as a live one.

When the database is read-only or suspended, the panel MUST present that prominently and MUST explain the consequence in the owner's terms — writes are rejected, or the application cannot connect — rather than only naming the state.

#### Scenario: Usage against allowance is shown
- **WHEN** the panel renders for a healthy database
- **THEN** it shows the measured size against the allowance and when that size was measured

#### Scenario: Read-only database explains the consequence
- **WHEN** the database is read-only
- **THEN** the panel says so prominently and explains that writes are being rejected

#### Scenario: Suspended database explains the consequence
- **WHEN** the database is suspended
- **THEN** the panel says so prominently and explains that the application cannot connect

#### Scenario: Never-measured database is not shown as empty
- **WHEN** the database has never been measured
- **THEN** the panel says the size is not yet known rather than displaying zero

### Requirement: The password is treated as a secret in the interface
The password MUST be masked until the reader reveals it, MUST NOT be rendered into the page in a form visible before that action, and MUST NOT be written to browser storage or to the URL.

Copying the password MUST be possible without first revealing it, so that handing it to a client does not require putting it on screen.

#### Scenario: Password is masked by default
- **WHEN** the panel first renders
- **THEN** the password is masked

#### Scenario: Password can be copied without revealing
- **WHEN** the reader copies the password without revealing it
- **THEN** the copied value is the password

#### Scenario: Secret is not persisted client-side
- **WHEN** the panel has rendered
- **THEN** the password has not been written to browser storage or to the address bar

### Requirement: An administrator sees the details without the password
When the platform withholds the password because the reader is an administrator rather than the owner, the panel MUST show the remaining details and MUST state that the password was withheld.

It MUST NOT show an empty field, a masked field that reveals nothing, or an error. An administrator diagnosing a deployment needs the database name, role and quota state; presenting the withheld password as a UI failure would send them looking for a bug.

#### Scenario: Administrator view
- **WHEN** an administrator opens the panel for another account's deployment
- **THEN** the database name, role name, quota state and usage are shown, and the panel states that the password is withheld

#### Scenario: Withholding is not an error
- **WHEN** the password is withheld
- **THEN** the panel presents no error state and offers no reveal affordance that cannot work
