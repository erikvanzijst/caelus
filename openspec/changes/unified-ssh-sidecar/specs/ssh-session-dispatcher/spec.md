## MODIFIED Requirements

### Requirement: A shell is served only where the session root is the application container
When a session requests no command and the declared session root is the application container, the dispatcher MUST place the user in that container: its filesystem, its executables, and its environment, as seen from the process running there.

A shell in the sidecar's own filesystem, holding none of the user's code, does not serve that request and MUST NOT be offered in its place.

When the declared session root is a mounted path, the dispatcher MUST refuse the session and say so. A session rooted at a read-only view of a product's data has no shell to offer: there is no code of the user's to run there, and the mount is not theirs to execute in. The refusal MUST name the reason rather than surfacing as an execution failure.

The refusal MUST be decided on the declaration. The dispatcher MUST NOT decide it by looking for an application process, because a pod that gained a shared process namespace for an unrelated reason would then begin granting shells it was never meant to.

#### Scenario: Shell sees the application's filesystem
- **WHEN** a user opens a session with no command against an application-rooted deployment whose application container is running
- **THEN** the resulting shell reads the application container's filesystem, not the sidecar's

#### Scenario: Shell sees the application's environment
- **WHEN** that shell inspects its environment
- **THEN** it carries the environment variables the application process was started with

#### Scenario: A volume-rooted session has no shell
- **WHEN** a user opens a session with no command against a volume-rooted deployment
- **THEN** the dispatcher refuses, naming the reason, and opens no session

#### Scenario: The refusal does not depend on the pod
- **WHEN** a volume-rooted deployment's pod shares a process namespace with an application container
- **THEN** a session with no command is still refused

### Requirement: The platform's database tooling is served only where the session root is the application container
A session requesting one of the platform's own tools — the PostgreSQL client and dump/restore tooling — MUST run it in the sidecar, where those tools live and where their connection details are, and MUST do so only where the declared session root is the application container.

The set of commands treated this way MUST be an explicit allowlist. Membership MUST be decided on the requested command itself and MUST NOT be inferrable from arguments a client controls.

Two separate conditions govern these commands and MUST be checked in order. Whether the tooling is offered at all follows from the declared session root: a volume-rooted session MUST decline it by name, whatever the container's environment holds. Whether there is a database to reach follows from the connection details: an application-rooted deployment without them MUST decline by naming the absence of a database, rather than running the tool and leaving the client to interpret a connection error.

Checking the environment alone would conflate the two, and would grant a database shell to any deployment that came to hold connection details for another reason.

Declining is still a routing decision on the command, so a command given as a path reaches the session root as any other does.

#### Scenario: Database client runs in the sidecar
- **WHEN** a session against an application-rooted deployment requests the PostgreSQL client
- **THEN** it runs in the sidecar and connects to the deployment's database

#### Scenario: Dump runs in the sidecar and streams
- **WHEN** such a session requests a dump
- **THEN** the dump runs in the sidecar and its output is delivered to the client unmodified

#### Scenario: Allowlist is not argument-driven
- **WHEN** a session requests a command whose arguments resemble an allowlisted tool but whose command is not one
- **THEN** it is not treated as a platform command

#### Scenario: A volume-rooted session is declined the tooling
- **WHEN** a session against a volume-rooted deployment requests a database tool
- **THEN** it is declined by name, and it is declined whether or not connection details are present in the container

#### Scenario: A platform command on a deployment with no database is declined
- **WHEN** a session against an application-rooted deployment with no database requests a database tool
- **THEN** the request is refused with a message naming the absence of a database, and no client connection error is produced instead

## ADDED Requirements

### Requirement: Any other command runs in the application container, and nowhere else
A session requesting a command that is not on the platform allowlist MUST run it in the application container when the declared session root is that container, so that ordinary remote-command behavior holds.

When the declared session root is a mounted path, the dispatcher MUST refuse the command and name the reason. There is no container to run it in, and running it in the sidecar would execute it somewhere the requester did not ask for.

#### Scenario: Arbitrary command runs where the application is
- **WHEN** a session against an application-rooted deployment requests a command that is not on the platform allowlist
- **THEN** the command runs in the application container

#### Scenario: A volume-rooted session runs no command
- **WHEN** a session against a volume-rooted deployment requests any command
- **THEN** it is refused by name, and nothing runs in the sidecar

### Requirement: File transfer is served from the sidecar, rooted at the session root
A session requesting file transfer MUST be served by the sidecar's own file-transfer tooling, confined to the declared session root, on every deployment that has a sidecar. The dispatcher MUST NOT look for a helper in the application container's filesystem and MUST NOT make the request's success depend on what a tenant's image contains.

This is the one session path both session roots serve, and it MUST be reached the same way for both: an application-rooted session transfers within the application container's filesystem, a volume-rooted session within its mount, and the difference is the root rather than the mechanism. One path used by every session is a path whose failures are found immediately.

#### Scenario: Transfer works against a minimal application image
- **WHEN** a client copies a file to an application-rooted deployment whose image contains no file-transfer helper
- **THEN** the file appears in the application container's filesystem

#### Scenario: Transfer on a volume-rooted deployment reads the mount
- **WHEN** a client lists and downloads from a volume-rooted deployment
- **THEN** it reads the mounted data, and cannot reach a path outside it

#### Scenario: One mechanism for both roots
- **WHEN** file transfer is served for either session root
- **THEN** the same sidecar-owned tooling serves it

## RENAMED Requirements

- FROM: `### Requirement: A session with no command opens a shell in the application container`
- TO: `### Requirement: A shell is served only where the session root is the application container`

- FROM: `### Requirement: A recognized platform command runs in the sidecar`
- TO: `### Requirement: The platform's database tooling is served only where the session root is the application container`

## REMOVED Requirements

### Requirement: Any other command runs in the application container

**Reason**: The requirement covered two different things: running a remote command, and file transfer, which worked only as a side effect of routing arbitrary commands into the application container. File transfer is now served directly and no longer depends on a command reaching a helper in the tenant's image, so the two are stated separately — as *Any other command runs in the application container, and nowhere else* and *File transfer is served from the sidecar, rooted at the session root* above.

**Migration**: None for a remote command, which routes as before on an application-rooted deployment. File transfer stops depending on the application image carrying a helper and begins working where it previously failed.
