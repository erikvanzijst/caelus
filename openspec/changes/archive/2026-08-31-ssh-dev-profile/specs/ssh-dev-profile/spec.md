## Purpose

`custom` deployments run code their owner wrote, against a database only the platform can
see, on a pod the owner cannot reach. This capability is the chart side of fixing that: the
`dev` access profile, which places the platform's SSH sidecar beside the application
container, grants it exactly the pod-level facilities it needs to enter and inspect that
container, and supplies it with the deployment's own database details and forward
allowlist. It is one of two profiles a product may declare, and no deployment runs both.

## ADDED Requirements

### Requirement: A product declares one access profile, and a deployment renders only that one
The library chart MUST offer two access profiles — `sftp` and `dev` — and a product MUST declare exactly one. A deployment MUST render the sidecar and Service of its declared profile, along with whatever additional objects that profile defines, and nothing belonging to the other.

Which additional objects those are is a property of the profile rather than of the chart contract. `sftp` renders a credentials Secret and an sshd-init ConfigMap because `atmoz/sftp` reads its user list, its trusted key and its startup script off disk. `dev` renders neither: the platform sidecar takes every input as an environment variable and writes its own `authorized_keys` and `sshd_config` at startup, so an object of either kind would be one nothing reads.

The profile is a property of the product, fixed when the chart renders, never a property of a connection or a choice a user makes at login. One deployment therefore has exactly one SSH server.

Which profile a deployment runs MUST NOT be settable by a tenant, through values or by any other tenant-supplied input. The `dev` profile grants a shell in the application container and the ability to trace its processes, so the choice is a platform decision about a product, not configuration a deployment carries.

#### Scenario: A tenant cannot change their deployment's profile
- **WHEN** a tenant supplies input attempting to select a different access profile
- **THEN** the rendered deployment runs the profile its product declares, unchanged

#### Scenario: A product on the dev profile renders only dev resources
- **WHEN** a product declaring the `dev` profile is rendered
- **THEN** its output contains the `dev` sidecar and no `atmoz/sftp` sidecar

#### Scenario: A product on the sftp profile is unchanged
- **WHEN** a product declaring the `sftp` profile is rendered
- **THEN** its output is equivalent to what it rendered before profiles existed

#### Scenario: No deployment runs both
- **WHEN** any deployment's pod is inspected
- **THEN** it contains at most one SSH server container

### Requirement: SSH resources are rendered on the declared profile, not on the presence of a PVC
A chart MUST render its profile's SSH resources whenever its product declares a profile, whether or not that product has a user-visible PVC. A product declaring no profile MUST render none.

This replaces the earlier rule that keyed rendering on exposable PVCs. That rule was correct while the only profile served files; it excludes the `dev` profile by construction, because `custom` has no persistent volume at all and is precisely the product this profile exists for.

#### Scenario: A product with no PVC still gets a sidecar
- **WHEN** a product declaring the `dev` profile and owning no PVC is deployed
- **THEN** its namespace contains the sidecar and its Service, and its release name is routable

#### Scenario: A product declaring no profile renders nothing
- **WHEN** a product that declares no access profile is deployed
- **THEN** its namespace contains no SSH resources and its release name is not routable

### Requirement: The dev profile runs the platform's SSH sidecar image at a pinned version
The `dev` profile MUST run the platform's own SSH sidecar image, referenced by an exact version tag supplied as a system value that a tenant cannot set. It MUST NOT reference the image by a moving tag.

A tenant-settable image reference here would let a tenant substitute the container that holds the platform's trusted key and enters their application; the reference belongs in the same category as the placeholder image, not in the category of the image a tenant builds.

#### Scenario: Image is pinned and platform-supplied
- **WHEN** a `dev` profile deployment is rendered
- **THEN** the sidecar's image is an exact version tag taken from a system value

#### Scenario: A tenant cannot choose the sidecar image
- **WHEN** a tenant supplies a value attempting to change the sidecar image
- **THEN** the rendered sidecar image is unaffected

### Requirement: The pod grants the sidecar exactly the facilities it needs, and no more
A pod running the `dev` profile MUST share its process namespace across containers. It MUST NOT run any container privileged, MUST NOT share the node's process namespace, and MUST NOT request any non-default capability.

Sharing the pod's process namespace is what lets the sidecar reach the application's filesystem and environment, at `/proc/<pid>/root` and `/proc/<pid>/environ`. It confers nothing outside the pod, because process identifiers resolve within the namespace that shares them — which is precisely why the pod's namespace is shared and the node's is not.

Entering the application container requires no added capability: the session chroots into the application process's root, which the default capability set already permits.

**Attaching a debugger or profiler is deliberately not offered yet.** `strace`, `gdb` and `py-spy` need `CAP_SYS_PTRACE`, and tenant namespaces enforce Pod Security `baseline`, which refuses every non-default capability at admission — a pod requesting one never schedules. Granting it requires raising the namespace's enforcement level for products on this profile, which is a change to what the platform guarantees about tenant pods and is decided separately from this capability.

The application container MUST NOT be granted anything by this profile.

#### Scenario: The sidecar sees the application's processes
- **WHEN** the sidecar enumerates processes
- **THEN** the application container's processes are visible to it

#### Scenario: The blast radius is the pod
- **WHEN** the sidecar attempts to reach a process outside its own pod
- **THEN** it cannot address one

#### Scenario: The pod is admitted under the tenant namespace's policy
- **WHEN** a `dev` profile deployment is applied to a tenant namespace
- **THEN** its pod is admitted and schedules, rather than being refused for requesting a non-default capability

#### Scenario: No privileged container and no added capability
- **WHEN** the pod specification is inspected
- **THEN** no container is privileged and no container requests a non-default capability

#### Scenario: The application container is unprivileged
- **WHEN** the application container's security context is inspected
- **THEN** it holds no capability the profile added

### Requirement: The chart supplies every runtime input the sidecar requires
The chart MUST supply the sidecar with all of the inputs its image declares as required: the platform's trusted public key, the forward allowlist, the release identity, and the deployment's database connection details. The sidecar exits rather than starting when any is missing, so an omission is a pod that will not run, not a pod that runs wrongly.

Every one of these MUST come from values the platform projects, never from values a tenant supplies. The connection details MUST reach the sidecar's own environment, so that database access does not depend on the application container being alive — which is the state a developer is most likely connecting to investigate.

#### Scenario: A rendered deployment starts
- **WHEN** a `dev` profile deployment is rendered and applied
- **THEN** the sidecar starts and serves, rather than exiting on a missing input

#### Scenario: Database tooling works with the application stopped
- **WHEN** the application container is not running and a developer runs the database client through the sidecar
- **THEN** it connects to the deployment's database

#### Scenario: The release identity is the deployment's own
- **WHEN** a session reports the release it landed on
- **THEN** the reported identity is that pod's release, not a value derived from the pod's name

#### Scenario: Tenant values cannot supply these inputs
- **WHEN** a tenant sets values attempting to change the trusted key, the forward allowlist, or the database details given to the sidecar
- **THEN** the rendered sidecar is unaffected

### Requirement: The forward allowlist admits the deployment's database and nothing else by default
The forward allowlist the chart supplies MUST name the deployment's own database endpoint, spelled exactly as a client will address it, and MUST NOT admit arbitrary destinations.

Tenant egress reaches the public internet on every port, so an unconstrained forwarder would be an authenticated open relay originating from the platform's address. The allowlist is the constraint that prevents it, and it is only effective if the spelling the chart renders and the spelling a client uses are identical.

#### Scenario: The database is forwardable
- **WHEN** a developer forwards a local port to the deployment's database endpoint as the chart spells it
- **THEN** the forward carries traffic

#### Scenario: Other destinations are refused
- **WHEN** a developer forwards to any destination the allowlist does not name
- **THEN** the forward is refused

#### Scenario: The spelling is the one clients use
- **WHEN** the platform documents the address a client should forward to
- **THEN** it is byte-identical to what the chart renders into the allowlist

### Requirement: The dev profile offers no SFTP subsystem and mounts no volume
The `dev` profile MUST NOT configure an SFTP subsystem of its own, MUST NOT chroot sessions, and MUST NOT mount any tenant volume into the sidecar.

File transfer is served by the session path: an ordinary remote command runs in the application container, so copying files works against the application's own filesystem with no additional configuration. A separate read-only view would be a second, weaker answer to a question the shell already answers, and chroot is incompatible with the port forwarding this profile exists to provide.

#### Scenario: Files can be copied without an SFTP configuration
- **WHEN** a developer copies a file to the deployment using a standard file-copy tool
- **THEN** it lands in the application container's filesystem

#### Scenario: No tenant volume is mounted into the sidecar
- **WHEN** the sidecar's volume mounts are inspected
- **THEN** none is a tenant data volume

### Requirement: Both profiles present the same Service to the edge
Whatever its profile, a deployment MUST expose its sidecar through a Service following the platform's single naming convention and listening on the platform's single sidecar port, because the edge derives a deployment's upstream address from that convention and knows nothing about profiles.

#### Scenario: The edge reaches a dev profile deployment
- **WHEN** a client connects with the username of a deployment on the `dev` profile
- **THEN** the edge resolves its upstream address by the same convention it uses for any other deployment

#### Scenario: Profiles are indistinguishable to the edge
- **WHEN** the edge resolves a deployment's upstream address
- **THEN** it requires no knowledge of which profile that deployment runs
