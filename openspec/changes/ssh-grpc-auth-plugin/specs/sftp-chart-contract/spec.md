## RENAMED Requirements

### Requirement: Per-deployment credentials Secret with stable password
- **FROM:** Per-deployment credentials Secret with stable password
- **TO:** Per-deployment credentials Secret carries no password

### Requirement: Per-deployment Service and Pipe route the username to the sidecar
- **FROM:** Per-deployment Service and Pipe route the username to the sidecar
- **TO:** Per-deployment Service targets the sidecar

## MODIFIED Requirements

### Requirement: Per-deployment Service targets the sidecar
The chart MUST render a ClusterIP Service targeting the sidecar's SSH port (2222), as part of the Helm release so it is created, upgraded, and deleted with the deployment. It MUST NOT render any routing object: the edge resolves where a username goes at connection time, so nothing in the release describes the route.

The whole of what a deployment contributes to SSH access is therefore inside its Helm release, and uninstalling the release removes all of it. No object survives the deployment, so nothing has to be swept for objects that do.

The Service MUST publish not-ready addresses, so its endpoints include the deployment's pod whenever that pod exists, irrespective of the pod's readiness. This Service does not front the application: it fronts an administrative sidecar whose availability is deliberately independent of the application's, so application readiness MUST NOT gate routing to it.

#### Scenario: Service is rendered by the chart
- **WHEN** the Helm release is installed
- **THEN** a ClusterIP Service targeting the sidecar on port 2222 exists in the deployment's namespace

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
