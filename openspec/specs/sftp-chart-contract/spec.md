## Purpose

Product wrapper charts must offer read-only file access to a deployment's user-visible data without exposing internal state or granting shell access. This capability defines the contract every product chart follows: it renders an `atmoz/sftp` sidecar that read-only-mounts exposable PVCs, provisions a credentials Secret carrying no password, and wires a Service the SFTP edge can reach. No routing object is rendered: the edge resolves where a username goes at connection time, so everything a deployment contributes to SSH access lives inside its Helm release. SSH resources are rendered because a product declares an access profile, not because it has a user-visible PVC; a product declaring no profile renders none at all, keeping the surface minimal. This capability covers the `sftp` profile and the Service both profiles share; the `dev` profile's own contract is `ssh-dev-profile`.

## Requirements

### Requirement: SFTP sidecar with read-only mounts of exposable PVCs
A product wrapper chart that declares user-visible PVCs MUST render an `atmoz/sftp` sidecar container in the application pod, mounting each exposable PVC with `readOnly: true` under the SFTP user's home directory (one subdirectory per PVC). PVCs holding database or other internal state (e.g., Postgres data directories) MUST NOT be mounted into the sidecar. The sidecar MUST be compatible with the Pod Security Admission `baseline` profile enforced on tenant namespaces.

#### Scenario: Exposable PVC is visible read-only
- **WHEN** a user logs in over SFTP to a deployment whose chart exposes a data PVC
- **THEN** the PVC's contents are listable and downloadable under a named subdirectory of the session root

#### Scenario: Database PVC is not visible
- **WHEN** a user logs in over SFTP to a deployment whose chart also declares a database PVC
- **THEN** no directory corresponding to the database PVC exists in the session

#### Scenario: Multiple exposable PVCs appear as sibling directories
- **WHEN** a deployment's chart exposes more than one PVC
- **THEN** each appears as its own subdirectory of the session root

### Requirement: Sessions are SFTP-only, read-only, with no shell
The sidecar MUST force the SFTP subsystem for all sessions (`ForceCommand internal-sftp`) and MUST run it read-only (`internal-sftp -R`), in addition to the kernel-level read-only mounts. Interactive shell access, command execution, and port forwarding MUST be unavailable. The session root (chroot top folder) MUST NOT be writable.

#### Scenario: Shell access is denied
- **WHEN** a user runs `ssh <username>@freepod.eu` requesting an interactive shell or a remote command
- **THEN** no shell or command execution is granted

#### Scenario: Writes are rejected
- **WHEN** an SFTP session attempts to upload, delete, rename, or chmod any path
- **THEN** the operation fails with a permission error

### Requirement: File access survives an unhealthy application container
SFTP reachability MUST NOT depend on the health of the application container sharing the pod. While the application container is failing, restarting, or crash-looping, a user who could previously reach the deployment's files over SFTP MUST still be able to reach them, provided the pod exists and the sidecar is running.

This is the case in which file access matters most: a tenant whose application is broken needs to retrieve or inspect their data. Withdrawing access at that moment is a defect, not a safety property. It MUST hold at every layer that could withdraw it, including whatever decides that a deployment is reachable at all.

#### Scenario: Application container is crash-looping
- **WHEN** a deployment's application container is in a crash-restart loop and its SFTP sidecar is running
- **THEN** an SFTP client connecting to the platform endpoint with a key registered on the owning account completes a session and can list and download the exposed PVC contents

#### Scenario: Application container fails to pull its image
- **WHEN** a deployment's application container cannot start because its image cannot be pulled, and its SFTP sidecar is running
- **THEN** SFTP access to the deployment's files is unaffected

#### Scenario: No pod exists
- **WHEN** a deployment has no pod at all, because it was never scheduled or the release was removed
- **THEN** SFTP access is unavailable, and this requirement imposes no obligation

### Requirement: The SFTP sidecar is liveness-probed
The sidecar MUST declare a liveness probe against its SSH port, so a sidecar whose `sshd` has stopped serving is restarted rather than left in place. Because application readiness no longer gates routing to the Service, the sidecar's own liveness is the only remaining mechanism that prevents connections being routed to a sidecar that cannot serve them.

The probe MUST test the SSH port's acceptance of connections and MUST NOT depend on the application container, on the exposed PVCs, or on any credential.

#### Scenario: Sidecar stops serving
- **WHEN** the sidecar's `sshd` is no longer accepting connections on its SSH port
- **THEN** the liveness probe fails and the sidecar container is restarted

#### Scenario: Probe is independent of the application
- **WHEN** the application container is unhealthy but the sidecar's `sshd` is accepting connections
- **THEN** the sidecar's liveness probe succeeds and the sidecar is not restarted

#### Scenario: Probe does not authenticate
- **WHEN** the liveness probe runs
- **THEN** it establishes no SFTP session and uses no deployment credentials

### Requirement: Products render SSH resources only when they declare an access profile
A chart MUST render a sidecar, a credentials Secret and a Service when its product declares an access profile, and MUST render none of them when it declares no profile.

The trigger is the declared profile, not the presence of a user-visible PVC. Keying it on PVCs was correct while the only profile served files, and it excludes the `dev` profile by construction: `custom` has no persistent volume and is the product that profile exists for.

A product on the `sftp` profile that declares no exposable PVC MUST still render nothing, because that profile's whole purpose is exposing one — its sidecar would offer an empty session.

#### Scenario: Zero-PVC product
- **WHEN** a product without exposable PVCs and without a declared profile is deployed
- **THEN** its namespace contains no SSH-related resources
- **AND** its release name is not routable at the SSH entry point

#### Scenario: Zero-PVC product on the dev profile
- **WHEN** a product without exposable PVCs that declares the `dev` profile is deployed
- **THEN** its namespace contains that profile's sidecar, Secret and Service, and its release name is routable

#### Scenario: sftp profile with nothing to expose
- **WHEN** a product declaring the `sftp` profile exposes no PVC
- **THEN** it renders no SSH resources

### Requirement: Per-deployment Service targets the sidecar
The chart MUST render a ClusterIP Service targeting the sidecar's SSH port (2222), as part of the Helm release so it is created, upgraded, and deleted with the deployment. It MUST NOT render any routing object: the edge resolves where a username goes at connection time, so nothing in the release describes the route.

The Service's name MUST follow the platform's single naming convention, which the SSH edge uses to derive a deployment's upstream address. The convention is shared with the edge and MUST NOT be changed on one side alone: a chart rendering a name the edge does not expect produces a deployment that authenticates and then reaches nothing.

The whole of what a deployment contributes to SSH access is therefore inside its Helm release, and uninstalling the release removes all of it. No object survives the deployment, so nothing has to be swept for objects that do.

The Service MUST publish not-ready addresses, so its endpoints include the deployment's pod whenever that pod exists, irrespective of the pod's readiness. This Service does not front the application: it fronts an administrative sidecar whose availability is deliberately independent of the application's, so application readiness MUST NOT gate routing to it.

#### Scenario: Service is rendered by the chart
- **WHEN** the Helm release is installed
- **THEN** a ClusterIP Service targeting the sidecar on port 2222 exists in the deployment's namespace

#### Scenario: Service name matches what the edge derives
- **WHEN** the edge derives a deployment's upstream address
- **THEN** it names the Service the chart rendered for that deployment

#### Scenario: Chart renders no routing object
- **WHEN** the chart's output is rendered
- **THEN** it contains no `Pipe` and no other object describing an SSH route

#### Scenario: Uninstall removes everything the deployment contributed
- **WHEN** the Helm release is uninstalled
- **THEN** the Service and sidecar are removed with it, the username stops being routable, and no object remains for the platform to clean up

#### Scenario: Service endpoints include a not-ready pod
- **WHEN** the deployment's pod exists but is not ready
- **THEN** the SFTP Service's endpoints still include that pod's address, and traffic to the Service reaches the sidecar

### Requirement: Per-deployment credentials Secret carries no password
The chart MUST render a credentials Secret in the deployment's namespace containing the SFTP username, which MUST equal the Helm release name, and the sidecar's user configuration. It MUST NOT generate or store a password, and the sidecar's user MUST be configured for key authentication only.

The Secret MUST carry the platform's public key as the sole key the sidecar trusts. It MUST NOT carry any private key, and MUST NOT carry any user's public key: the keys that authenticate a person are resolved at the edge, and never reach the tenant.

The sidecar's user MUST be the Helm release name, and the chart MUST NOT offer products a way to choose a different one. The edge derives the upstream username from the deployment's own record and reads no cluster object to learn it, so a chart free to name that user something else would produce a deployment the edge cannot log in to — a failure visible only on a live connection, and only to the affected product.

Everything in the Secret is therefore either the release's own name or a public key, so the tenant's pod holds no secret material for this feature at all — that and the sidecar's own generated host key.

#### Scenario: No password is generated
- **WHEN** the chart is rendered or installed
- **THEN** no password is generated, stored in the Secret, or written into the sidecar's user configuration

#### Scenario: Sidecar trusts the platform's public key
- **WHEN** the credentials Secret is inspected
- **THEN** it contains the platform's public key and no private key

#### Scenario: No user keys reach the tenant namespace
- **WHEN** a deployment's namespace is inspected
- **THEN** it contains no registered user's public key

#### Scenario: Password authentication is unavailable at the sidecar
- **WHEN** a connection to the sidecar attempts password authentication
- **THEN** it is refused

#### Scenario: The sidecar's user is the release name
- **WHEN** any product's chart is rendered
- **THEN** the sidecar's configured user is the Helm release name, and no product overrides it
