## MODIFIED Requirements

### Requirement: Ingress restricted to the shared edge and the deployment's own namespace
The baseline policy MUST permit ingress only from the shared ingress controller (Traefik), from the platform SFTP router (sshpiper), and from pods within the same namespace. The ingress allowance for the shared edge MUST NOT restrict ports, so that products may expose their service on any port without per-product configuration. The ingress allowance for the SFTP router MUST be restricted to the SFTP sidecar port (2222/TCP) only. All other ingress MUST be denied.

#### Scenario: Ingress from the shared ingress controller is allowed
- **WHEN** the shared Traefik ingress controller connects to a pod in the deployment namespace
- **THEN** the connection is allowed on any port

#### Scenario: Ingress from the SFTP router is allowed on the sidecar port
- **WHEN** an sshpiper pod connects to a pod in the deployment namespace on port 2222/TCP
- **THEN** the connection is allowed

#### Scenario: Ingress from the SFTP router to other ports is denied
- **WHEN** an sshpiper pod connects to a pod in the deployment namespace on a port other than 2222
- **THEN** the connection is denied

#### Scenario: Intra-namespace ingress is allowed
- **WHEN** a pod in the deployment namespace connects to another pod in the same namespace
- **THEN** the connection is allowed

#### Scenario: Ingress from another deployment namespace is denied
- **WHEN** a pod in a different deployment namespace connects to a pod in the deployment namespace
- **THEN** the connection is denied

### Requirement: Cluster-specific isolation inputs are configurable
The cluster-specific inputs to the baseline policy MUST be configurable rather than hard-coded, including: the baseline policy name, the ingress controller's namespace and pod label, the SFTP router's namespace, pod label, and sidecar port, the shared mailer's namespace, pod label, and port, the cluster DNS service IP, and the list of internal CIDR ranges excluded from public-internet egress. Configuration MUST provide defaults that match the current cluster.

#### Scenario: Overriding a cluster-specific input
- **WHEN** an operator overrides an isolation input (for example, the mailer namespace or an excluded CIDR range) via settings
- **THEN** the rendered baseline policy reflects the overridden value

#### Scenario: Overriding the SFTP router selector
- **WHEN** an operator overrides the SFTP router's namespace, pod label, or sidecar port via settings
- **THEN** the rendered baseline policy's SFTP ingress rule reflects the overridden values
