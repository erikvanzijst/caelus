## MODIFIED Requirements

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
- **THEN** the forward is refused

#### Scenario: A container with no allowlist refuses every forward
- **WHEN** a container is supplied with no allowlist and a client forwards to any destination
- **THEN** the forward is refused

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

### Requirement: Configuration is supplied at runtime and validated before the server starts
Everything that varies per deployment — the trusted public key, the permitted forward destinations, the identity the session banner reports, and the deployment's database connection details — MUST be supplied to the container at startup rather than built in.

Supplied configuration MUST be validated before the SSH server starts, and a container given invalid configuration MUST fail loudly rather than start in a degraded state. The contract MUST be documented, since it is the interface a chart will target.

Not every input is required. Those describing the server itself — the trusted key, the banner identity, the login account — are; those describing a facility a deployment may not have — the forward allowlist, the database connection details — are not. The documentation MUST say which are which, because the difference is what decides whether an absent value is a pod that will not start or a deployment that simply has no database.

#### Scenario: Configuration contract is documented
- **WHEN** an operator or a chart author needs to run the image
- **THEN** the repository documents every input the image accepts, which are required, and what each does

#### Scenario: Invalid configuration fails fast
- **WHEN** the container is given a malformed forward allowlist
- **THEN** it exits with a non-zero status and an error identifying the input, rather than starting with forwarding misconfigured
