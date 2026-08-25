## MODIFIED Requirements

### Requirement: Egress permits only the deployment's own namespace, cluster DNS, the shared mailer, the shared database pooler, and the public internet
The baseline policy MUST permit egress to: pods within the same namespace; cluster DNS (kube-dns) on port 53 (UDP and TCP); the shared SMTP relay service; the shared database pooler on its client port; and the public internet. All other egress MUST be denied.

The pooler allowance is part of the single fleet-wide policy and is therefore present in every deployment namespace, including those whose product has no relational storage. Reachability is not authorization: a deployment without provisioned credentials cannot authenticate, and one deployment's credentials do not grant access to another's database.

#### Scenario: Intra-namespace egress is allowed
- **WHEN** a pod in the deployment namespace connects to another pod in the same namespace
- **THEN** the connection is allowed

#### Scenario: DNS egress is allowed
- **WHEN** a pod in the deployment namespace queries cluster DNS
- **THEN** the query to kube-dns on port 53 (UDP or TCP) is allowed

#### Scenario: Shared mailer egress is allowed
- **WHEN** a pod in the deployment namespace connects to the shared SMTP relay
- **THEN** the connection to the mailer service is allowed

#### Scenario: Database pooler egress is allowed
- **WHEN** a pod in the deployment namespace connects to the shared database pooler on its client port
- **THEN** the connection is allowed

#### Scenario: Pooler egress is allowed on the client port only
- **WHEN** a pod in the deployment namespace connects to the pooler on any other port
- **THEN** the connection is denied

#### Scenario: Pooler is reachable from a deployment without relational storage
- **WHEN** a pod belonging to a deployment whose product has no relational storage connects to the pooler
- **THEN** the connection is allowed at the network layer
- **AND** the deployment holds no credentials with which to authenticate

#### Scenario: Public internet egress is allowed
- **WHEN** a pod in the deployment namespace connects to a public (non-internal) address
- **THEN** the connection is allowed

### Requirement: Egress denies all internal networks and cloud metadata
The public-internet egress allowance MUST exclude every internal address range: the private ranges `10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16`, and the link-local range `169.254.0.0/16`. As a result, a deployment MUST NOT be able to reach other deployments' pods or services, the cluster service network (including the Kubernetes API server), the cluster node, the LAN, or the cloud metadata endpoint, except via the explicit DNS, mailer, database pooler, and intra-namespace allowances.

The tenant PostgreSQL server itself is not among the allowances. A deployment MUST NOT be able to reach it directly, which is what makes the pooler the only path to a database.

#### Scenario: Cross-deployment traffic is denied
- **WHEN** a pod in the deployment namespace connects to a pod or service in another deployment's namespace
- **THEN** the connection is denied

#### Scenario: Kubernetes API server is unreachable
- **WHEN** a pod in the deployment namespace connects to the Kubernetes API server (via its cluster IP or the node address)
- **THEN** the connection is denied

#### Scenario: Node, LAN, and metadata endpoint are unreachable
- **WHEN** a pod in the deployment namespace connects to the cluster node IP, another LAN host, or the link-local metadata endpoint `169.254.169.254`
- **THEN** the connection is denied

#### Scenario: The tenant PostgreSQL server is unreachable directly
- **WHEN** a pod in the deployment namespace connects to the tenant PostgreSQL server rather than the pooler
- **THEN** the connection is denied
