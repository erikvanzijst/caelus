## Purpose

Caelus deployments run as isolated Helm releases, and users need a way to browse and download their deployment's files. This capability provides the shared, platform-owned SSH edge that terminates inbound SFTP connections and routes them to the correct per-deployment sidecar. A single SSH reverse proxy (sshpiperd) per environment exposes one public port, routes connections by SSH username via `Pipe` custom resources, relays password authentication to the upstream, and keeps environments separated at the network layer. Routing updates live as deployments come and go, and a stable proxy host key keeps clients' `known_hosts` entries valid across proxy redeploys.

## Requirements

### Requirement: One public SSH entry point per environment with configurable ports
Each environment (prod, dev) MUST expose a single SSH endpoint for its deployments, terminating at that environment's SSH reverse proxy (sshpiperd) running in a platform namespace. The environments share one public IPv4 address and SSH has no hostname indication, so distinct ports are the only environment discriminator. The user-facing endpoints are `freepod.eu:22` (prod) and `dev.freepod.eu:23` (dev); the home router translates these to the internal chain, where every hop MUST avoid port 22 because both the homelab host and the cluster node retain their system OpenSSH there: router :22 → HAProxy :2222 → cluster node :2222 (prod), and router :23 → HAProxy :2223 → cluster node :2223 (dev). The cluster-side ports MUST be Terraform variables per environment workspace, defaulting to 2222 (prod) and 2223 (dev). The edge path MUST be plain TCP passthrough; no TLS or HTTP layer is involved. The per-environment proxy MUST be provisioned declaratively via Terraform in `tf/app/` (workspace-scoped); the cluster-scoped Pipe CRD MUST be installed once via `tf/deps/`.

#### Scenario: Client connects to the prod endpoint
- **WHEN** an SFTP client connects to `freepod.eu` on port 22
- **THEN** the connection traverses router :22 → HAProxy :2222 → cluster node :2222 unmodified
- **AND** the client completes an SSH handshake with the prod sshpiperd

#### Scenario: Client connects to the dev endpoint
- **WHEN** an SFTP client connects to `dev.freepod.eu` on port 23
- **THEN** the connection traverses router :23 → HAProxy :2223 → cluster node :2223 unmodified
- **AND** the client completes an SSH handshake with the dev sshpiperd

#### Scenario: Host system SSH is unaffected
- **WHEN** an administrator connects to the homelab host or the cluster node on their local port 22
- **THEN** they reach the host's system OpenSSH, not sshpiperd

#### Scenario: Operator changes an environment's cluster-side port
- **WHEN** an operator changes the SSH port variable for a workspace and applies Terraform (plus the matching HAProxy backend)
- **THEN** the environment's SSH endpoint is reachable end-to-end without changes to charts, Pipes, or the other environment

### Requirement: Connections are routed to deployments by SSH username
The proxy MUST route each incoming SSH connection to a per-deployment upstream selected by the SSH username, using `Pipe` custom resources watched across all namespaces. A username with no matching Pipe MUST be rejected during authentication without revealing whether the username exists.

#### Scenario: Known username routes to its deployment
- **WHEN** a client authenticates with a username matching a Pipe's `from.username`
- **THEN** the connection is proxied to the Service referenced by that Pipe's `to.host`

#### Scenario: Unknown username is rejected
- **WHEN** a client attempts to authenticate with a username that matches no Pipe
- **THEN** authentication fails with a generic authentication error

### Requirement: Routes update live without restarts or session disruption
Creating, modifying, or deleting a Pipe MUST take effect without restarting sshpiperd, and MUST NOT disturb established SSH sessions on other routes. Deploying or deleting an application MUST NOT require any change to the proxy deployment itself.

#### Scenario: New deployment becomes reachable
- **WHEN** a new deployment's Helm release creates a Pipe while other users have active SFTP sessions
- **THEN** the new username becomes routable without a proxy restart
- **AND** all established sessions continue uninterrupted

#### Scenario: Deleted deployment stops being routable
- **WHEN** a deployment is deleted and its Pipe is removed with its namespace
- **THEN** subsequent connection attempts with that username are rejected

### Requirement: Password authentication is relayed to the upstream
The proxy MUST relay the client-supplied password to the upstream SFTP endpoint for validation and MUST NOT store or validate user credentials itself. Public-key authentication MUST NOT be offered in v1.

#### Scenario: Correct password grants access
- **WHEN** a client authenticates with a routable username and the password from the deployment's credentials Secret
- **THEN** the upstream OpenSSH validates the password and the session is established

#### Scenario: Wrong password is rejected
- **WHEN** a client authenticates with a routable username and an incorrect password
- **THEN** the upstream rejects authentication and the client receives an authentication failure

### Requirement: Environment separation
A connection accepted by one environment's proxy MUST NOT reach the SFTP endpoint of a deployment belonging to the other environment, even when the username matches a Pipe from that other environment (both proxies watch Pipes cluster-wide). Enforcement MUST NOT depend on routing-layer filtering alone: each environment's tenant NetworkPolicy admits only that environment's proxy pods.

#### Scenario: Cross-environment access is denied
- **WHEN** a client connects to the dev SSH port using a prod deployment's username and password
- **THEN** the connection to the prod deployment's sidecar is denied at the network layer and the session is not established

### Requirement: Stable proxy host key
The proxy MUST present a host key sourced from a Kubernetes Secret that persists across pod restarts, upgrades, and redeploys, so that clients' `known_hosts` entries remain valid. Upstream (sidecar) host keys MUST NOT be presented to clients and MAY change freely.

#### Scenario: Host key survives a proxy redeploy
- **WHEN** the sshpiperd Deployment is deleted and re-created by Terraform
- **THEN** clients connecting afterwards observe the same host key as before
