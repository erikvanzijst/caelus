# cli-database-status Specification

## Purpose

The `freepod` client is where a developer already works, and a database's health is
something they need while their code is in front of them rather than after switching to a
browser. This capability adds a `db` command group whose first member, `freepod db
status`, reports the deployment's database: which database and role it is, the password
that owns it, and how much of its allowance is used, in what state.

It deliberately does **not** report an address or a connection URL. The pooler is
reachable only from inside the cluster, so a URL printed here would connect from nowhere
the reader is standing; the URL that will connect is the one `freepod db proxy` composes
around its own local address in the SSH forwarding change. What `status` reports is exactly
the part that stays true on both sides of that tunnel — the database's identity, its
credential, and its health.

## Requirements

### Requirement: `freepod db status` reports the deployment's database
The client MUST provide a `db` command group with a `status` subcommand that reads the platform's database details for the deployment recorded in the project file, and reports the database name, the role name, the password, the database's measured size, its allowance, when that size was measured, and its current state.

The command MUST resolve its deployment the same way the other project-scoped commands do — from the project file, refusing the same ways that can be wrong — and MUST NOT accept a deployment named on the command line.

#### Scenario: Reporting a provisioned database
- **WHEN** a developer runs `freepod db status` in a project whose deployment has relational storage
- **THEN** the database name, role name, password, size, allowance, measurement time and state are reported

#### Scenario: No deployment
- **WHEN** the command runs in a directory whose project file records no deployment
- **THEN** it fails as the other project-scoped commands do, saying so rather than reporting an empty database

### Requirement: The command reports no address and no connection URL
`freepod db status` MUST NOT print the pooler host, the pooler port, or a composed `postgresql://` connection URL, and MUST NOT offer a flag that prints one.

The address is in-cluster and cannot be reached from the machine the command ran on. Printing it — as fields to copy, or assembled into a URL — produces something that looks like the input to `psql` and is not, which costs a developer a failed connection and a support question before they learn it was never reachable. The forwarding change introduces the address that works, on the command that establishes it, and there is then exactly one connection URL in the product rather than two that differ.

The database name, role and password are reported because they are unchanged by forwarding: a client pointed at a future tunnel needs exactly those, in the field-by-field form a graphical client asks for.

#### Scenario: No address is printed
- **WHEN** a developer runs `freepod db status` against a provisioned database
- **THEN** the output contains neither the pooler host nor the pooler port

#### Scenario: No URL is printed
- **WHEN** any invocation of `freepod db status` succeeds
- **THEN** its output contains no `postgresql://` connection URL

### Requirement: The password is masked unless it is asked for
`freepod db status` MUST mask the password in its default output and MUST print it only when the invocation explicitly asks, through a `--show-password` flag.

The password is returned to the owner and the client is running as the owner, so this is not a disclosure rule; it is about not writing a live database credential into terminal scrollback for an invocation whose usual purpose is to ask how much room is left. The masked output MUST make clear that a value exists and how to reveal it, rather than presenting the mask as though it were the value.

#### Scenario: Default output masks
- **WHEN** a developer runs `freepod db status`
- **THEN** the output does not contain the password
- **AND** it says how to reveal it

#### Scenario: Explicit reveal
- **WHEN** a developer runs `freepod db status --show-password`
- **THEN** the password is printed

### Requirement: The command states how the database is reached
The command MUST state that the database is reachable from the running application and not from the machine the command ran on.

Reporting a role and a password with no address invites the question the statement answers. It MUST describe what is true now, without promising forwarding that has not shipped, and it is a diagnostic rather than a result, so it MUST go to stderr under the client's stream discipline.

#### Scenario: Reachability is stated
- **WHEN** the command reports the database's details
- **THEN** it states that the database is reachable from the running application rather than from this machine

### Requirement: A degraded database is reported in the owner's terms
The command MUST report a read-only or suspended database prominently and in terms of its consequence — writes rejected, the application unable to connect — rather than reporting a state name alone, and MUST distinguish a database that has never been measured from one measured at zero bytes.

A tenant reaching for this command is often doing so because writes started failing. The state name is the answer, and it is only useful if it says what it means.

#### Scenario: Read-only
- **WHEN** the deployment's database has been switched to read-only for exceeding its allowance
- **THEN** the command reports that state and that writes are being rejected

#### Scenario: Suspended
- **WHEN** the deployment's database has been suspended
- **THEN** the command reports that state and that the application cannot connect

#### Scenario: Never measured
- **WHEN** the database has never been measured
- **THEN** the command says the size is not yet known rather than reporting zero

### Requirement: A product without relational storage is not an error
When the platform reports that the deployment's product offers no relational storage, `freepod db status` MUST say so plainly and exit successfully, rather than presenting it as a failure of the command or of the platform. The question was answered: this deployment has no database.

#### Scenario: Product without a database
- **WHEN** a developer runs `freepod db status` in a project whose product has no relational storage
- **THEN** the command reports that this deployment has no database and exits successfully
