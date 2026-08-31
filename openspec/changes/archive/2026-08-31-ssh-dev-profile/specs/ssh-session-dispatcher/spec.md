## MODIFIED Requirements

### Requirement: A recognized platform command runs in the sidecar
A session requesting one of the platform's own tools — the PostgreSQL client and dump/restore tooling — MUST run it in the sidecar, where those tools live and where their connection details are.

The set of commands treated this way MUST be an explicit allowlist. Membership MUST be decided on the requested command itself and MUST NOT be inferrable from arguments a client controls.

The tools are present in every sidecar; the connection details are not. On a deployment with no database the dispatcher MUST decline these commands with a message naming the absence of a database, rather than run them and leave the client to interpret a connection error. Declining is still a routing decision on the command, so a command given as a path reaches the application container as any other does.

#### Scenario: Database client runs in the sidecar
- **WHEN** a session requests the PostgreSQL client
- **THEN** it runs in the sidecar and connects to the deployment's database

#### Scenario: Dump runs in the sidecar and streams
- **WHEN** a session requests a dump
- **THEN** the dump runs in the sidecar and its output is delivered to the client unmodified

#### Scenario: Allowlist is not argument-driven
- **WHEN** a session requests a command whose arguments resemble an allowlisted tool but whose command is not one
- **THEN** it is not treated as a platform command

#### Scenario: A platform command on a deployment with no database is declined
- **WHEN** a session requests a database tool on a deployment that has no database
- **THEN** the request is refused with a message naming the absence of a database, and no client connection error is produced instead
