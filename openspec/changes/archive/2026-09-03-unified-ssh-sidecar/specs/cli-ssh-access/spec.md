## MODIFIED Requirements

### Requirement: Four commands over the deployment the project names
The client MUST provide a command opening a session in the deployment's application container, a command forwarding a local port to the deployment's database, a command opening an interactive database session, and a command copying files and directories between the local machine and the deployment's application container.

Each MUST resolve which deployment it acts on the same way every other project-scoped command does, and MUST fail with the same guidance when run outside a project or against a deployment that does not exist.

#### Scenario: Shell reaches the application container
- **WHEN** a user runs the shell command in a project whose deployment is running
- **THEN** they are placed in an interactive session in that deployment's application container

#### Scenario: Copy reaches the application container
- **WHEN** a user runs the copy command in a project whose deployment is running
- **THEN** the file is read from or written to that deployment's application container, not the sidecar

### Requirement: The shell command runs a given command instead of opening a session
The shell command MUST accept a command to run in the application container, and MUST then run it there and exit rather than opening an interactive session. The exit code MUST be the remote command's own.

The platform already serves this path — the session dispatcher routes a requested command into the application container — so a client that only opened sessions was the narrower half of a facility that exists. Words are passed to `ssh` as given and joined by it, so the container's own shell does the interpreting and a quoted pipeline stays whole, which is the behavior anyone reaching for this already knows from `ssh`.

Words after the command MUST be passed through as the remote command's, never parsed as the client's own options, because a command's flags are not the client's to claim.

A terminal MUST NOT be allocated for a given command unless the user asks for one, and MUST be allocated for an interactive session. A pty rewrites what passes through it — line endings translated, standard error folded into standard output — so allocating one for a command whose output is redirected or piped corrupts it; a full-screen program needs one, which is why asking MUST remain possible.

#### Scenario: A command runs in the application container
- **WHEN** a user runs the shell command with a command in a project whose deployment is running
- **THEN** the command runs in the application container and the client exits with the command's own exit code

#### Scenario: The command's own options are not the client's
- **WHEN** the given command carries flags the client also defines
- **THEN** they reach the remote command unparsed

#### Scenario: Output that is redirected is not rewritten
- **WHEN** a user redirects the output of a command run this way
- **THEN** no terminal was allocated for it, and the bytes are the command's own

#### Scenario: A full-screen program is given a terminal
- **WHEN** a user asks for a terminal alongside a command
- **THEN** one is allocated for it

#### Scenario: Database session needs no local client
- **WHEN** a user runs the database shell command
- **THEN** an interactive database session opens without a PostgreSQL client being installed locally

#### Scenario: Outside a project
- **WHEN** any of these commands is run outside a project directory
- **THEN** the client reports that in the same terms as its other project-scoped commands

## ADDED Requirements

### Requirement: A copy names its remote side, and the direction follows from it
The copy command MUST take a source and a destination, exactly one of which is marked as being on the deployment. The direction of the transfer MUST follow from which one is marked, and MUST NOT be a separate flag the user can set inconsistently with the paths they gave.

Which side is marked MUST be decided by a rule that no local path can satisfy by accident. A path carrying the marker MAY also name a deployment, and MUST then name the one the project names; naming a different one MUST be refused rather than resolved, because the client acts on one deployment and silently ignoring the name would make it look otherwise.

A copy with neither side marked, or with both marked, MUST be refused before connecting, naming which of the two it was. Neither means the user meant a local copy their own shell already does; both means a deployment-to-deployment transfer, which this command does not offer.

A remote path that is not absolute MUST be resolved the way it would be in a session opened by the shell command, so that the two commands agree about what a bare relative path means.

#### Scenario: The marked side is the deployment's
- **WHEN** a user copies a local file to a marked remote path
- **THEN** the file is written into the application container at that path

#### Scenario: The direction reverses with the marking
- **WHEN** a user copies a marked remote path to a local one
- **THEN** the file is read from the application container and written locally

#### Scenario: Neither side is marked
- **WHEN** a user gives two local paths
- **THEN** the client refuses, saying neither path names the deployment, and connects to nothing

#### Scenario: Both sides are marked
- **WHEN** a user gives two remote paths
- **THEN** the client refuses, saying it does not copy between deployments, and connects to nothing

#### Scenario: A local path containing a colon stays local
- **WHEN** a user names a local file whose own name contains a colon
- **THEN** it is treated as a local path, not as a marked one

#### Scenario: A marked path naming another deployment is refused
- **WHEN** a marked path names a deployment other than the one the project names
- **THEN** the client refuses rather than acting on the project's deployment

#### Scenario: A relative remote path agrees with the shell
- **WHEN** a user copies to a relative remote path
- **THEN** it resolves to the same location a shell session would resolve it to

### Requirement: A copy carries a file or a directory tree over the platform's own file transfer
A copy MUST use the file-transfer facility the platform's sidecar serves, which is available on every deployment the client can open a session against and requires nothing to be present in the user's own image.

A directory MUST be copied as the tree beneath it, preserving the relative structure and the file modes of its members, and MUST NOT require a flag to say so. A single file MUST arrive as a single file. Ownership and timestamps are not preserved, and the client MUST NOT imply otherwise.

The client MUST NOT reimplement the transfer protocol, and MUST report the absence of the local tooling it drives as a missing prerequisite naming what to install, as it does for `ssh` itself.

#### Scenario: A copy works against an unmodified deployment
- **WHEN** a user copies to and from a deployment whose image was built by the platform and contains no file-transfer tooling of its own
- **THEN** both transfers succeed

#### Scenario: A directory arrives as a tree
- **WHEN** a user copies a directory containing nested files and an executable
- **THEN** the tree arrives with its structure intact and the executable still executable, with no flag given to ask for recursion

#### Scenario: A binary file round-trips
- **WHEN** a user copies a binary file out of the deployment and back in
- **THEN** the bytes at each end are identical

#### Scenario: Missing local tooling is a named prerequisite
- **WHEN** the copy command runs on a machine lacking the tooling it drives
- **THEN** the client names the missing prerequisite and what to install, and does not fail with an unhandled error

### Requirement: A failed copy is not reported as a successful one
A copy that does not complete MUST exit non-zero and say what did not arrive. A partial transfer MUST NOT be reported as success.

Local conditions the client can see before connecting — a source that does not exist, a destination directory that is not writable — MUST be reported before a connection is attempted, so a predictable failure does not cost a round trip and does not read as a platform problem.

A remote path that does not exist MUST be reported as the deployment's, distinguishably from a local path that does not exist, because the two are told apart only by which side the client says it looked on.

A copy MUST inherit the connection assembly the client's other SSH commands use: the single registered key, the pinned edge host key, and the checks that explain a predictable refusal rather than letting it surface as an opaque one.

#### Scenario: A missing local source is caught first
- **WHEN** a user copies from a local path that does not exist
- **THEN** the client says so and attempts no connection

#### Scenario: A missing remote path names the deployment
- **WHEN** a user copies from a remote path that does not exist
- **THEN** the client reports that the path was not found in the deployment, distinguishably from a local miss

#### Scenario: An interrupted transfer fails
- **WHEN** a transfer is interrupted before it completes
- **THEN** the client exits non-zero and does not report the copy as done

#### Scenario: A copy offers one key and verifies the edge
- **WHEN** a user with several keys in their agent runs a copy
- **THEN** exactly one key is offered to the edge, and the edge's host key is checked against the published value

## RENAMED Requirements

- FROM: `### Requirement: Three commands over the deployment the project names`
- TO: `### Requirement: Four commands over the deployment the project names`
