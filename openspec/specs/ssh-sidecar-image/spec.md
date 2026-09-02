# ssh-sidecar-image Specification

## Purpose

The `dev` access profile needs an SSH server that can forward a TCP connection to the
database pooler, host a shell into the application container beside it, and run the
platform's PostgreSQL tooling at the server's own version. This capability defines that
image: what it contains, how its SSH server is configured, what configuration it takes at
startup, and what it refuses to run without. The image is a self-contained artifact; the
pod-level settings it depends on, and the chart that supplies its configuration, are
defined elsewhere.

## Requirements

### Requirement: The image is platform-owned, versioned, and never re-pushed
The image MUST be built from a build context in this repository, pinned to explicit base and package versions so a rebuild of a given tag produces a functionally identical image, and published under an immutable version tag.

An already-published tag MUST NOT be overwritten. A change to the image is a new version, and consumers are repointed at it. The publishing path MUST enforce this rather than only documenting it: an attempt to push a version the registry already holds MUST fail.

The image MUST NOT contain any credential, key, or tenant data. Everything it needs to authenticate a session arrives at runtime.

#### Scenario: Rebuild is reproducible
- **WHEN** the image is rebuilt from the same source at the same version
- **THEN** it provides the same SSH server behavior, dispatcher behavior, and tool versions

#### Scenario: Re-pushing a published version is refused
- **WHEN** a publish is attempted for a version tag the registry already holds
- **THEN** it fails without overwriting the published image

#### Scenario: No baked secrets
- **WHEN** the published image is inspected
- **THEN** it contains no private key, no authorized key, no password, and no tenant data

### Requirement: The image carries its own version, and consumers pin it exactly
The image's version MUST be declared in its build context, and that declaration MUST be the single input from which the publishing path derives the tag it pushes. A version is therefore a reviewable edit in this repository, not an argument someone types at a terminal.

That version MUST be independent of the version of any chart that consumes the image. The two move on their own cadences: a chart changes for reasons that do not touch the image, and the coupling runs one way — the image reference lives in the chart, so a new image cannot reach a deployment except through a chart change.

A consumer MUST reference the image by an exact version tag and MUST NOT reference it by a moving tag. A moving tag makes the version a pod runs a function of when that pod last restarted and what its node had cached, which is not a property any deployment should have.

#### Scenario: Published tag comes from the declared version
- **WHEN** the image is published
- **THEN** the tag it carries is the version declared in its build context

#### Scenario: Chart version and image version are not required to agree
- **WHEN** a consuming chart is changed without any change to the image
- **THEN** the chart takes a new version and continues to reference the existing image version

#### Scenario: Consumers pin an exact version
- **WHEN** a consumer references the image
- **THEN** it names an exact version tag rather than a moving one

### Requirement: The SSH server accepts public keys only
The SSH server MUST authenticate by public key alone. Password authentication, keyboard-interactive authentication, and any other interactive fallback MUST be disabled, and root login by password MUST be refused.

The set of trusted keys MUST be supplied at runtime and MUST NOT be baked into the image. The image trusts exactly the key material it is given — in normal operation the single public key of the platform's SSH edge — and no other.

#### Scenario: Password authentication is refused
- **WHEN** a client attempts password authentication against the server
- **THEN** the attempt is refused and no password prompt succeeds

#### Scenario: Only the supplied key authenticates
- **WHEN** a client presents a public key that was not supplied to the container at startup
- **THEN** authentication fails

#### Scenario: The supplied key authenticates
- **WHEN** a client presents the public key supplied to the container at startup
- **THEN** authentication succeeds

### Requirement: The server refuses to start without a trusted key
If no trusted public key is supplied at startup, the container MUST fail to start and MUST say why. It MUST NOT start an SSH server that no one can authenticate to, because that failure is indistinguishable from a network problem and would be diagnosed as one.

#### Scenario: Missing key material
- **WHEN** the container is started with no trusted public key
- **THEN** it exits with a non-zero status and an error naming the missing configuration

#### Scenario: Unusable key material
- **WHEN** the container is started with key material that is not a valid SSH public key
- **THEN** it exits with a non-zero status rather than starting with an empty trust set

### Requirement: Sessions are not chrooted
The SSH server MUST NOT chroot sessions. Chroot is incompatible with the port forwarding this profile exists to provide: the process that opens a forwarded connection runs inside the chroot, where there is no resolver configuration, and name resolution for the forward's target fails.

#### Scenario: Forwarding resolves its target
- **WHEN** a client opens a forwarded connection to a target addressed by hostname
- **THEN** the server resolves that hostname and connects, rather than failing to resolve it

### Requirement: Forwarding is local-only and constrained to an allowlist
The server MUST permit local port forwarding and MUST refuse remote port forwarding. Permitted forward destinations MUST be an explicit allowlist supplied at runtime; a forward to any other destination MUST be refused.

Agent forwarding, X11 forwarding, and gateway ports MUST be disabled.

An allowlist is required rather than recommended because the pod's egress reaches the public internet on every port: an unconstrained forwarder would be an authenticated open TCP relay originating from the platform's address.

The allowlist itself is optional, because a deployment may have nothing to forward to. A container supplied with none MUST refuse every forward, and MUST express that refusal explicitly in the server's configuration rather than by omitting the constraint: the server's own default is to permit forwarding to any destination, so an omitted constraint would turn "nothing to allow" into "allow everything".

#### Scenario: Permitted destination is forwarded
- **WHEN** a client forwards to a destination in the supplied allowlist
- **THEN** the connection is established and carries traffic

#### Scenario: Other destinations are refused
- **WHEN** a client forwards to a destination absent from the allowlist
- **THEN** the server refuses the channel

#### Scenario: Remote forwarding is refused
- **WHEN** a client requests a remote forward
- **THEN** the request is refused

#### Scenario: Agent forwarding is unavailable
- **WHEN** a client requests agent forwarding
- **THEN** the request is refused

### Requirement: Forward destinations are matched as the client writes them
A permitted destination MUST be matched against the destination string as the client requested it, and the allowlist MUST therefore be expressed in the same form a client will use. The image MUST document this, because a mismatch between the allowlist's spelling of a host and the client's produces a refusal that reads like an authorization failure.

#### Scenario: Equivalent spellings are not interchangeable
- **WHEN** the allowlist names a destination in one form and a client requests an equivalent but differently spelled form
- **THEN** the behavior is documented, so an operator configuring the allowlist knows the two must agree

### Requirement: The image carries PostgreSQL client tooling matching the tenant cluster
The image MUST include the PostgreSQL command-line client and dump/restore tools at a major version no older than the tenant database cluster's, so that dumps taken through this sidecar are never rejected for a version mismatch.

Running these tools server-side is the point: a developer's local `pg_dump` older than the server aborts, and that failure is not fixable from the client.

#### Scenario: Dump tooling is not older than the server
- **WHEN** the image's dump tool version is compared against the tenant cluster's server version
- **THEN** the tool's major version is greater than or equal to the server's

#### Scenario: Tools are present and runnable
- **WHEN** the client and dump tools are invoked inside the image
- **THEN** each reports its version and exits successfully

### Requirement: Database tooling takes its connection details from the environment
The PostgreSQL tools MUST connect using the deployment's database connection details as supplied in the container's own environment, so that invoking the client with no arguments opens a session against that deployment's database.

The sidecar MUST NOT depend on the application container being alive to learn these details. A developer connects precisely when the application is broken, and connection details read from a process that is crash-looping would be unavailable exactly then.

The connection details are optional **as a set**. The toolbox is a facility this image offers, not a precondition it imposes: a container supplied with none MUST start and MUST serve every other session path, and requests for the database tools MUST be declined with a message naming the absence of a database rather than run and left to fail as a client connection error.

A container supplied with an *incomplete* set MUST exit at startup, naming what was supplied and what is missing. Nothing supplied means a deployment without a database; something supplied means the projection that should have supplied the rest is broken, and a container that started anyway would surface that inside the client at the moment someone needed the database and furthest from its cause.

#### Scenario: Client with no arguments connects to the deployment's database
- **WHEN** the PostgreSQL client is invoked with no arguments in a container supplied with the deployment's connection details
- **THEN** it attempts a connection to that database rather than to a default or a local socket

#### Scenario: Availability does not depend on the application container
- **WHEN** the application container is not running
- **THEN** the sidecar still has the connection details it needs

#### Scenario: A container with no database serves every other session path
- **WHEN** a container is supplied with none of the connection details
- **THEN** it starts and serves sessions, and only the database tooling is unavailable

#### Scenario: Database tools are declined rather than left to fail
- **WHEN** a client requests a database tool on a container supplied with no connection details
- **THEN** the request is refused with a message naming the absence of a database

#### Scenario: An incomplete set of connection details fails fast
- **WHEN** a container is supplied with some but not all of the connection details
- **THEN** it exits with a non-zero status naming what is missing, rather than starting

### Requirement: Host keys are generated at startup and are not persisted
The server MUST generate its host key at container start. Host keys MUST NOT be baked into the image, because every deployment would then share one, and MUST NOT be required to persist across restarts.

Only a modern elliptic-curve host key is required. Generating large RSA host keys on every start delays the port opening for seconds with no benefit here, since the client-facing host identity is the edge's and the connection from the edge to this server does not pin the sidecar's key.

#### Scenario: Each container has its own host key
- **WHEN** two containers are started from the same image
- **THEN** they present different host keys

#### Scenario: The port opens promptly
- **WHEN** the container starts
- **THEN** the SSH port begins accepting connections without waiting on large-key generation

### Requirement: The server listens on the platform's sidecar port
The server MUST listen on the platform's conventional sidecar SSH port rather than the default SSH port, matching the port the platform's tenant network policy admits from the SSH edge.

#### Scenario: Server is reachable on the sidecar port
- **WHEN** a client connects to the container on the platform's sidecar port
- **THEN** an SSH handshake completes

### Requirement: Configuration is supplied at runtime and validated before the server starts
Everything that varies per deployment — the trusted public key, the permitted forward destinations, the release identity, and the deployment's database connection details — MUST be supplied to the container at startup rather than built in.

Supplied configuration MUST be validated before the SSH server starts, and a container given invalid configuration MUST fail loudly rather than start in a degraded state. The contract MUST be documented, since it is the interface a chart will target.

The release identity MUST be taken as **two** inputs, both required: the number a user sees, which the session banner reports, and the platform's own identifier for the release, which the image records where it can be read beside the logs that identifier keys. Neither substitutes for the other, and a container given only one MUST refuse to start: with only the identifier the banner would name the release in a spelling no user can look up, and with only the number nothing the pod writes could be correlated with the release it belongs to.

Not every input is required. Those describing the server itself — the trusted key, both spellings of the release identity, the login account — are; those describing a facility a deployment may not have — the forward allowlist, the database connection details — are not. The documentation MUST say which are which, because the difference is what decides whether an absent value is a pod that will not start or a deployment that simply has no database.

#### Scenario: Configuration contract is documented
- **WHEN** an operator or a chart author needs to run the image
- **THEN** the repository documents every input the image accepts, which are required, and what each does

#### Scenario: Invalid configuration fails fast
- **WHEN** the container is given a malformed forward allowlist
- **THEN** it exits with a non-zero status and an error identifying the input, rather than starting with forwarding misconfigured

#### Scenario: Half a release identity is not a release identity
- **WHEN** the container is given either spelling of the release identity but not the other
- **THEN** it exits with a non-zero status and an error naming the missing one

### Requirement: The image runs as root and holds no capability beyond its purpose
The SSH server runs as root because the dispatcher must read another container's process filesystem and enter it. The image MUST NOT require additional privilege beyond what the pod grants it, MUST NOT assume it can mount filesystems, and MUST NOT require a privileged container.

The image MUST behave correctly, and report clearly, when the pod-level facilities it can use are absent rather than assuming they are present.

#### Scenario: No privileged mode required
- **WHEN** the image runs without privileged mode and without mount capability
- **THEN** the SSH server starts and serves normally

#### Scenario: Absent pod facilities are reported, not assumed
- **WHEN** the image runs in a pod that does not share a process namespace with an application container
- **THEN** it starts and serves, and reports the limitation when a session depends on that facility
