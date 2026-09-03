## MODIFIED Requirements

### Requirement: Configuration is supplied at runtime and validated before the server starts
Everything that varies per deployment — the trusted public key, the session root, the permitted forward destinations, the release identity, and the deployment's database connection details — MUST be supplied to the container at startup rather than built in.

Supplied configuration MUST be validated before the SSH server starts, and a container given invalid configuration MUST fail loudly rather than start in a degraded state. The contract MUST be documented, since it is the interface a chart will target.

The release identity MUST be taken as **two** inputs, both required: the number a user sees, which the session banner reports, and the platform's own identifier for the release, which the image records where it can be read beside the logs that identifier keys. Neither substitutes for the other, and a container given only one MUST refuse to start: with only the identifier the banner would name the release in a spelling no user can look up, and with only the number nothing the pod writes could be correlated with the release it belongs to.

Not every input is required. Those describing the server itself — the trusted key, the session root, both spellings of the release identity, the login account — are; those describing a facility a deployment may not have — the forward allowlist, the database connection details — are not. The documentation MUST say which are which, because the difference is what decides whether an absent value is a pod that will not start or a deployment that simply has no database.

#### Scenario: Configuration contract is documented
- **WHEN** an operator or a chart author needs to run the image
- **THEN** the repository documents every input the image accepts, which are required, and what each does

#### Scenario: Invalid configuration fails fast
- **WHEN** the container is given a malformed forward allowlist
- **THEN** it exits with a non-zero status and an error identifying the input, rather than starting with forwarding misconfigured

#### Scenario: Half a release identity is not a release identity
- **WHEN** the container is given either spelling of the release identity but not the other
- **THEN** it exits with a non-zero status and an error naming the missing one

#### Scenario: No session root is not a default
- **WHEN** the container is given no session root
- **THEN** it exits with a non-zero status naming the missing input, rather than choosing one

### Requirement: The server itself does not chroot, and forwarding is unaffected by confinement
The SSH server MUST NOT be configured to chroot connections before a session starts. A connection that opens no session — a port forward — MUST NOT be confined at all: the process that opens a forwarded connection would otherwise run inside a filesystem with no resolver configuration, and name resolution for the forward's target would fail.

Confinement to the session root is applied to a session once it has started, and therefore reaches only sessions. This is what lets one server both confine file transfer to a session root and forward to a named destination.

#### Scenario: Forwarding resolves its target
- **WHEN** a client opens a forwarded connection to a target addressed by hostname
- **THEN** the server resolves that hostname and connects, rather than failing to resolve it

#### Scenario: A confined session does not confine a forward
- **WHEN** a client opens a forward and a session on one connection
- **THEN** the session is confined to the session root and the forward reaches its destination

## ADDED Requirements

### Requirement: The session root is declared, and the image serves nothing outside it
The image MUST take the session root as a declared input naming one of two things: a path the container has mounted, or the filesystem of the application container sharing the pod. It MUST confine every session to that root, and MUST NOT serve any path outside it.

A confined session runs a program, and that program's own prerequisites MUST be reachable inside the confinement. Where the declared root cannot supply them — a mounted path holds the product's data and nothing else — the image MUST supply them itself, and a session MUST then begin at the declared path rather than wherever those prerequisites live. What the image supplies MUST hold nothing of the tenant's and nothing of the platform's: it exists so that a transfer can run, and carries no credential, no configuration and no data.

The image MUST decide what a session may do from this declaration alone, never by testing what the pod happens to expose. A capability that is granted because a facility was found is a capability that appears when unrelated configuration changes.

A declared application-container root that cannot be resolved — because the pod does not share a process namespace, or no application process is identifiable — MUST be reported as such and MUST NOT fall back to serving the container's own filesystem. The sidecar's filesystem holds none of the user's data and is not a lesser version of what was asked for.

#### Scenario: A path outside the session root is unreachable
- **WHEN** a session requests a path outside its session root by any spelling, including one that traverses upward
- **THEN** the request is refused and no path outside the root is read or written

#### Scenario: The declaration decides, not the pod
- **WHEN** a container declaring a mounted-path session root runs in a pod that shares a process namespace
- **THEN** its sessions are still rooted at the mounted path

#### Scenario: A session begins at the declared path
- **WHEN** a session opens against a deployment whose declared root is a mounted path
- **THEN** it starts at that path, and the paths it reports for the product's data are the ones the product documents

#### Scenario: What the image supplies to run a transfer holds nothing of anyone's
- **WHEN** a session inspects everything reachable outside the declared path
- **THEN** it finds only what the transfer program itself requires, and no credential, configuration or data of the tenant's or the platform's

#### Scenario: An unresolvable application root is reported
- **WHEN** a container declaring an application-container root cannot identify the application process
- **THEN** the session reports that, naming the likely cause, and no session is served from the sidecar's own filesystem

### Requirement: File transfer is served by the image's own tooling
The image MUST serve file transfer from tooling it carries itself, chrooted into the session root. It MUST NOT look for a file-transfer helper in the application container's filesystem, and MUST NOT make file transfer conditional on what a tenant's image contains.

A tenant's image is theirs and commonly contains no such helper — the image the platform's own build pipeline produces does not. Serving from the sidecar makes file transfer a property of the platform rather than of what a user happened to install, and gives one code path exercised by every session on every deployment rather than a fallback that is rarely taken and therefore rarely known to work.

#### Scenario: Transfer works against a minimal image
- **WHEN** a client copies a file to or from a deployment whose application image contains no file-transfer tooling
- **THEN** the transfer succeeds

#### Scenario: Transfer lands in the session root
- **WHEN** a client uploads a file to an application-rooted deployment
- **THEN** it appears in the application container's own filesystem, not in the sidecar's

#### Scenario: The tenant's image is not consulted
- **WHEN** a session requests file transfer
- **THEN** the server uses its own tooling regardless of what the application image contains

### Requirement: Whether a session may write follows from the filesystem
Whether a session may modify what it can reach MUST be taken from the filesystem of the declared path rather than from a separate setting. A declared path that is mounted read-only MUST be served read-only.

It MUST be taken from the declared path specifically, and not from whatever the confinement happens to be rooted at: where the image supplies a session's prerequisites itself, those live in the container's own writable layer, and reading the answer from there would report a read-only mount as writable.

Two independent statements of the same intent can disagree, and the one that would be wrong is the one inside the container. The kernel already knows the answer, refuses a write regardless of the user the session runs as, and cannot be overridden by a container holding no capability to remount.

#### Scenario: A read-only root is served read-only
- **WHEN** a session's root is a read-only mount
- **THEN** the server declines write operations, and a write attempted anyway is refused by the filesystem

#### Scenario: A writable root is writable
- **WHEN** a session's root is a writable filesystem
- **THEN** the session may create and modify files within it

#### Scenario: Ownership does not decide readability
- **WHEN** the session root holds files owned by another user with restrictive modes
- **THEN** the session reads them, without the container being told which user owns them

## RENAMED Requirements

- FROM: `### Requirement: Sessions are not chrooted`
- TO: `### Requirement: The server itself does not chroot, and forwarding is unaffected by confinement`
