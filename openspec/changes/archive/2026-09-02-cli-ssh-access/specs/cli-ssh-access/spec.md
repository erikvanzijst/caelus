## Purpose

A developer with a `custom` deployment can already reach it over SSH, if they know four
things the platform knows and they do not: the edge's address, that their username is the
deployment name, which of their keys is registered, and the exact spelling of their
database's in-cluster address. This capability is the client that supplies all four — a
shell in the application container, a forwarded database port, and a server-side database
session — and, because the edge deliberately refuses without saying why, the diagnosis a
user gets when one of them fails.

## ADDED Requirements

### Requirement: Three commands over the deployment the project names
The client MUST provide a command opening an interactive session in the deployment's application container, a command forwarding a local port to the deployment's database, and a command opening an interactive database session.

Each MUST resolve which deployment it acts on the same way every other project-scoped command does, and MUST fail with the same guidance when run outside a project or against a deployment that does not exist.

#### Scenario: Shell reaches the application container
- **WHEN** a user runs the shell command in a project whose deployment is running
- **THEN** they are placed in an interactive session in that deployment's application container

#### Scenario: Database session needs no local client
- **WHEN** a user runs the database shell command
- **THEN** an interactive database session opens without a PostgreSQL client being installed locally

#### Scenario: Outside a project
- **WHEN** any of the three is run outside a project directory
- **THEN** the client reports that in the same terms as its other project-scoped commands

### Requirement: The client offers exactly one key, the registered one this machine holds
The client MUST present a single identity when it connects: the key recorded for this environment, and no other. It MUST NOT let the user's agent or default key files supply additional identities.

The edge answers *every* offered key with a partial success, so a client that offers several exhausts the server's authentication budget and is refused before reaching the right one. Offering one key is therefore a correctness requirement, not a courtesy.

When no local record exists, the client MUST attempt recovery by fingerprint before giving up, and MUST record what it finds so the next invocation needs no search.

#### Scenario: Only the registered key is offered
- **WHEN** a user with several keys in their agent runs any of these commands
- **THEN** exactly one key is offered to the edge

#### Scenario: A missing record is recovered
- **WHEN** the local record is absent but a registered key's public half is present on this machine
- **THEN** the client finds it by fingerprint, uses it, and records it

#### Scenario: No usable key
- **WHEN** no registered key can be found on this machine
- **THEN** the client says so and names the command that registers one, without attempting a connection

### Requirement: Failures are diagnosed from the platform, never inferred from the refusal
The edge refuses uniformly and discloses nothing about why. The client MUST NOT present a guess at the cause as though it were the cause, and MUST NOT translate a refusal into a specific explanation it cannot support.

Before connecting, the client MUST check what the platform does report — whether the account has a registered key, and whether the deployment is in a state that accepts connections — and MUST explain a predictable failure in those terms rather than letting it surface as an opaque refusal.

When a connection is refused despite those checks passing, the client MUST say that the platform refused, list what it verified, and MUST NOT assert a cause.

#### Scenario: Account with no registered key
- **WHEN** a user whose account has no registered key runs any of these commands
- **THEN** the client explains that before connecting and names the command that registers one

#### Scenario: Deployment that cannot accept connections
- **WHEN** the deployment is in a state the platform does not admit connections for
- **THEN** the client says so rather than attempting a connection that will be refused

#### Scenario: Unexplained refusal is reported honestly
- **WHEN** the platform refuses a connection although the client's checks passed
- **THEN** the client reports the refusal and what it checked, and does not claim a specific cause

#### Scenario: A broken deployment is still reachable
- **WHEN** the deployment's application container is failing but the platform admits connections to it
- **THEN** the client connects, because that is the state these commands exist for

### Requirement: The client verifies the edge rather than trusting it on sight
The client MUST verify the edge's host key against the value the platform publishes, using its own known-hosts store rather than the user's, and MUST NOT accept an unverified host key on first use.

A first connection that trusts whatever answers is the one connection worth attacking, and the platform's host key is stable and knowable, so there is no reason to guess at it.

A host key that does not match the published value MUST be treated as a failure to be reported, never as something to be accepted and recorded.

#### Scenario: First connection is verified
- **WHEN** a user connects for the first time on a machine
- **THEN** the edge's key is checked against the published value and no prompt to trust it appears

#### Scenario: Mismatch is refused
- **WHEN** the edge presents a key other than the published one
- **THEN** the client refuses to connect and reports the mismatch

#### Scenario: The user's own known-hosts is untouched
- **WHEN** the client connects
- **THEN** the user's personal known-hosts file is neither read as authority nor written to

### Requirement: The forwarded address is the platform's, spelled the platform's way
The address the client forwards to MUST be the one the platform reports for that deployment's database, used verbatim. The client MUST NOT reconstruct, normalise, or abbreviate it.

The forward allowlist at the far end matches the destination as the client wrote it and resolves it afterwards, so any difference in spelling produces a refusal that reads like an authorization failure rather than a typo.

#### Scenario: The reported address is used unchanged
- **WHEN** the client opens a forward
- **THEN** the destination it requests is byte-identical to what the platform reported

#### Scenario: A refused forward is explained as such
- **WHEN** a forward is refused by the far end
- **THEN** the client explains that the destination was not permitted, distinguishably from an authentication failure

### Requirement: The proxy prints a usable connection URL and holds the tunnel in the foreground
The forwarding command MUST run in the foreground until interrupted, and MUST print a connection URL addressing the **local** end of the tunnel, carrying the deployment's own database name and credentials.

The URL MUST be correctly encoded, so that a credential containing characters with meaning in a URL yields a URL that parses back to the same values rather than one that silently differs.

The URL MUST go to standard output and everything the client says about itself to standard error, so the URL survives being piped or captured.

#### Scenario: URL addresses the local port
- **WHEN** the forward is established
- **THEN** the printed URL names the local address and port, not the platform's internal one

#### Scenario: URL round-trips
- **WHEN** a credential contains characters requiring encoding in a URL
- **THEN** parsing the printed URL yields exactly the credential the platform reported

#### Scenario: URL is capturable
- **WHEN** the command's standard output is captured
- **THEN** it contains the URL and none of the client's own narration

#### Scenario: Interrupt closes the tunnel
- **WHEN** the user interrupts the command
- **THEN** the tunnel closes and the local port is released

### Requirement: A local port is chosen when one is not given
The forwarding command MUST accept a local port and MUST choose a free one when none is given, reporting which it chose. It MUST NOT fail merely because a conventional default is occupied, and MUST report clearly when a port the user explicitly asked for is unavailable.

#### Scenario: Default port is in use
- **WHEN** no port is given and the conventional one is occupied
- **THEN** the client binds a free port and reports it in the URL it prints

#### Scenario: Requested port is in use
- **WHEN** the user names a port that is unavailable
- **THEN** the client reports that specifically rather than choosing a different one silently

### Requirement: The system SSH client is required and its absence is explained
The client MUST use the system `ssh` executable rather than implementing the protocol, and MUST report its absence as a missing prerequisite naming what to install.

#### Scenario: `ssh` is not installed
- **WHEN** any of these commands runs on a machine with no `ssh` on the path
- **THEN** the client reports the missing prerequisite by name and does not fail with an unhandled error

### Requirement: No credential or key material is written to the terminal beyond the URL
Beyond the connection URL the forwarding command prints for the user to use, a command MUST NOT print, log, or echo a private key, and MUST NOT write credential material to a location the user did not ask for.

#### Scenario: Verbose output stays clean
- **WHEN** any of these commands runs with verbose output enabled
- **THEN** no private key material appears

#### Scenario: The shell commands print no credential
- **WHEN** the shell or database-shell command runs
- **THEN** no database credential is printed
