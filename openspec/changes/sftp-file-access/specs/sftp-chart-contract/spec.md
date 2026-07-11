## ADDED Requirements

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

#### Scenario: Pipe routes to the deployment's Service
- **WHEN** the Helm release is installed
- **THEN** a Pipe exists in the deployment's namespace whose `from.username` is the release name and whose `to.host` references the deployment's SFTP Service on port 2222

#### Scenario: Uninstall removes routing
- **WHEN** the Helm release is uninstalled
- **THEN** the Pipe, Service, and sidecar are removed with it

### Requirement: Products without exposable PVCs render no SFTP resources
A chart with no user-visible PVCs MUST render no sidecar, no credentials Secret, no Service, and no Pipe.

#### Scenario: Zero-PVC product
- **WHEN** a product without exposable PVCs is deployed
- **THEN** its namespace contains no SFTP-related resources
- **AND** its release name is not routable at the SSH entry point
