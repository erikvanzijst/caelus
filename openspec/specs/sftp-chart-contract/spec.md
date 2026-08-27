## Purpose

Product wrapper charts must offer read-only file access to a deployment's user-visible data without exposing internal state or granting shell access. This capability defines the contract every product chart follows: it renders an `atmoz/sftp` sidecar that read-only-mounts exposable PVCs, provisions per-deployment credentials with a stable password, and wires a Service and `Pipe` so the SFTP edge can route the deployment's username to its sidecar. Products that expose no user-visible PVCs render no SFTP resources at all, keeping the surface minimal and the routing table free of dead entries.

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

### Requirement: Per-deployment credentials Secret with stable password
The chart MUST render a credentials Secret in the deployment's namespace containing the SFTP username and password. The username MUST equal the Helm release name. The password MUST be generated randomly on first install and MUST remain unchanged across subsequent Helm upgrades (Helm `lookup` pattern: reuse the existing Secret's value when present). The sidecar's user configuration MUST be derived from the same value so the Secret and the SSH daemon cannot diverge.

#### Scenario: Password is stable across upgrades
- **WHEN** a deployment is upgraded via the reconciler after initial install
- **THEN** the credentials Secret's password is unchanged
- **AND** existing credentials continue to authenticate

#### Scenario: Credentials work immediately after install
- **WHEN** a deployment reaches ready state for the first time
- **THEN** the username and password from its credentials Secret authenticate successfully over SFTP

### Requirement: Per-deployment Service and Pipe route the username to the sidecar
The chart MUST render a ClusterIP Service targeting the sidecar's SSH port (2222) and a `Pipe` custom resource mapping `from.username` (the release name) to that Service. Both MUST be part of the Helm release so they are created, upgraded, and deleted with the deployment.

The Service MUST publish not-ready addresses, so its endpoints include the deployment's pod whenever that pod exists, irrespective of the pod's readiness. This Service does not front the application: it fronts an administrative sidecar whose availability is deliberately independent of the application's, so application readiness MUST NOT gate routing to it.

#### Scenario: Pipe routes to the deployment's Service
- **WHEN** the Helm release is installed
- **THEN** a Pipe exists in the deployment's namespace whose `from.username` is the release name and whose `to.host` references the deployment's SFTP Service on port 2222

#### Scenario: Uninstall removes routing
- **WHEN** the Helm release is uninstalled
- **THEN** the Pipe, Service, and sidecar are removed with it

#### Scenario: Service endpoints include a not-ready pod
- **WHEN** the deployment's pod exists but is not ready
- **THEN** the SFTP Service's endpoints still include that pod's address, and traffic to the Service reaches the sidecar

### Requirement: File access survives an unhealthy application container
SFTP reachability MUST NOT depend on the health of the application container sharing the pod. While the application container is failing, restarting, or crash-looping, a user who could previously reach the deployment's files over SFTP MUST still be able to reach them, provided the pod exists and the sidecar is running.

This is the case in which file access matters most: a tenant whose application is broken needs to retrieve or inspect their data. Withdrawing access at that moment is a defect, not a safety property.

#### Scenario: Application container is crash-looping
- **WHEN** a deployment's application container is in a crash-restart loop and its SFTP sidecar is running
- **THEN** an SFTP client connecting to the platform endpoint with the deployment's credentials completes a session and can list and download the exposed PVC contents

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

### Requirement: Products without exposable PVCs render no SFTP resources
A chart with no user-visible PVCs MUST render no sidecar, no credentials Secret, no Service, and no Pipe.

#### Scenario: Zero-PVC product
- **WHEN** a product without exposable PVCs is deployed
- **THEN** its namespace contains no SFTP-related resources
- **AND** its release name is not routable at the SSH entry point
