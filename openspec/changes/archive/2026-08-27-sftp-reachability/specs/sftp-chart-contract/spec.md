## MODIFIED Requirements

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

## ADDED Requirements

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
