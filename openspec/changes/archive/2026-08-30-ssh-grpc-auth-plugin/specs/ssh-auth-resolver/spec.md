## Purpose

The SSH edge has to decide, for every incoming connection, whether the key a client offered
may open the deployment its username names, and where that deployment's sidecar lives. This
capability defines the component that answers, what it answers from, what it refuses, and
how it behaves when it cannot answer at all. It exists so that the answer is derived from
the platform's records at the moment it is needed, rather than copied ahead of time into
cluster objects that must then be kept in repair.

## ADDED Requirements

### Requirement: The resolver answers the edge's routing and authentication question per connection
The platform MUST provide a resolver that the SSH edge consults on each connection, receiving the SSH username the client presented and the public key it offered, and returning either the upstream sidecar to connect to and the credential to present there, or a refusal.

The resolver MUST derive its answer from the platform's own records at the time of the request. It MUST NOT depend on a copy of those records held elsewhere — in a cluster object, a rendered file, or a cache that can outlive a change to the underlying record — because any such copy is a second source of truth that can disagree with the first and grant access the platform's records no longer authorize.

Consulting the resolver MUST NOT require the edge to be restarted or reconfigured when a deployment or a key is created or removed.

#### Scenario: A connection is resolved from current records
- **WHEN** a client connects with a username and offers a public key
- **THEN** the edge obtains the upstream target and the upstream credential from the resolver, derived from the platform's records as they stand at that moment

#### Scenario: A new deployment is reachable without reconfiguring the edge
- **WHEN** a deployment is created and its owner connects to it
- **THEN** the connection resolves without the edge having been restarted or reconfigured

#### Scenario: No copy of the answer exists to go stale
- **WHEN** the cluster is inspected
- **THEN** no object holds a routing record or a projection of any account's keys for this purpose

### Requirement: Access requires a key registered on the account that owns the deployment
The resolver MUST admit a connection only when the offered public key is registered on the account that owns the deployment the username names. A key registered on one account MUST NOT open another account's deployment, and a key registered on no account MUST NOT open anything.

Losing ownership of a deployment MUST end access to it, because the account consulted is the deployment's current owner.

#### Scenario: Owner's registered key is admitted
- **WHEN** a client offers a key registered on the account owning the deployment its username names
- **THEN** the connection is admitted and proxied to that deployment's sidecar

#### Scenario: Another account's key is refused
- **WHEN** a client offers a key registered on a different account than the one owning the deployment
- **THEN** the connection is refused

#### Scenario: An unregistered key is refused
- **WHEN** a client offers a key registered on no account
- **THEN** the connection is refused

#### Scenario: Ownership change moves access
- **WHEN** a deployment's ownership changes
- **THEN** the new owner's keys are admitted and the previous owner's are refused

### Requirement: Revocation is effective on the next connection, with nothing to refresh
Removing a key from an account MUST stop it opening any of that account's deployments from the next connection attempt onward, without any further platform action: no projection to rewrite, no object to update, no sweep to run, and no reconcile or redeploy of any deployment.

Because the resolver reads the account's keys rather than a copy of them, there MUST be no interval during which a removed key still authenticates, and the platform MUST NOT rely on a periodic repair to make a revocation take effect.

#### Scenario: A revoked key stops working immediately
- **WHEN** a user removes a key and makes no other change
- **THEN** the next connection offering that key is refused

#### Scenario: Revocation needs no deployment change
- **WHEN** a key is removed
- **THEN** no deployment is reconciled or redeployed, and no cluster object is written, for the revocation to take effect

#### Scenario: A newly registered key works immediately
- **WHEN** a user registers a key and makes no other change
- **THEN** the next connection offering that key is admitted

### Requirement: A deployment that no longer exists stops being routable by that fact alone
The resolver MUST refuse a username that names no deployment, and MUST refuse one whose deployment is not in a state that permits access. Ceasing to be routable MUST be a consequence of the deployment's own record, not of a separate cleanup step that could fail or be skipped.

A username MUST NOT resolve to a deployment other than the one that record names, so a name later reused by a different deployment carries no access from the earlier one.

#### Scenario: A deleted deployment is not routable
- **WHEN** a deployment is deleted and a client connects with its username
- **THEN** the connection is refused, without any routing object having had to be removed

#### Scenario: An unknown username is refused
- **WHEN** a client connects with a username naming no deployment
- **THEN** the connection is refused

#### Scenario: There is no orphaned routing state to detect
- **WHEN** the platform sweeps for cluster objects no row accounts for
- **THEN** routing state is not among the classes it must look for, because none is created

### Requirement: Refusals are uniform and disclose nothing
Every refusal MUST be indistinguishable to the client, whatever its cause: an unknown username, a deployment that is not accessible, a key registered to another account, a key registered nowhere, or the resolver being unable to answer.

The resolver MUST NOT reveal whether a username exists, whether an account has any registered keys, or why a particular attempt failed. Operators MUST be able to distinguish these causes from the platform's own records of the attempt.

#### Scenario: Unknown username and wrong key are indistinguishable
- **WHEN** a client connects with a username that does not exist, and separately with a valid username and an unregistered key
- **THEN** both attempts fail in the same way, and nothing in either response distinguishes them

#### Scenario: Operators can tell the causes apart
- **WHEN** an operator investigates a failed attempt
- **THEN** the platform's own record of it identifies which cause applied

### Requirement: Only public-key authentication is offered
The resolver MUST offer public-key authentication and MUST NOT offer password, keyboard-interactive, or unauthenticated access. Password authentication MUST be unavailable at the edge as a property of what the resolver advertises, not merely as configuration that could be re-enabled by an operator error.

#### Scenario: Password authentication is not offered
- **WHEN** a client queries which authentication methods the edge accepts
- **THEN** only public-key authentication is offered

#### Scenario: A password attempt cannot succeed
- **WHEN** a client attempts password authentication against the edge
- **THEN** it is refused, whatever password is supplied

### Requirement: The upstream credential is held by the resolver and never by a tenant
The credential the edge presents to a deployment's sidecar MUST be held by the platform and supplied by the resolver. It MUST NOT be derived from anything the client supplied, and the client's own credential MUST NOT be replayed upstream.

No tenant namespace MUST hold that credential. A tenant namespace holds only the public half that its sidecar trusts, which grants its holder nothing.

#### Scenario: The upstream leg uses the platform's own credential
- **WHEN** the edge opens the upstream connection to a sidecar
- **THEN** it authenticates with a credential supplied by the resolver

#### Scenario: The client's credential is not forwarded
- **WHEN** a client authenticates to the edge
- **THEN** what it presented is not used against the upstream

#### Scenario: No tenant namespace holds the upstream credential
- **WHEN** any tenant namespace is inspected
- **THEN** it holds no credential that authenticates the platform to a sidecar

### Requirement: The resolver fails closed, and its health is the edge's health
When the resolver cannot reach the records it needs, or cannot answer for any other reason, it MUST refuse the connection. It MUST NOT admit a connection on incomplete information, fall back to a previously cached answer, or default to any less restrictive behavior.

Because every SSH connection depends on it, the resolver's availability MUST be treated as the SSH edge's availability: it MUST be monitored as a user-facing dependency, and its failure MUST be distinguishable from a user's key being wrong.

#### Scenario: An unavailable dependency refuses rather than admits
- **WHEN** the resolver cannot read the platform's records
- **THEN** connections are refused, and none is admitted on partial information

#### Scenario: A stale answer is never reused
- **WHEN** the resolver has previously answered for a connection and its records later become unreachable
- **THEN** the earlier answer is not reused to admit a new connection

#### Scenario: Resolver failure is visible as an outage
- **WHEN** the resolver is failing
- **THEN** the platform surfaces it as an SSH edge outage, distinguishable from clients presenting unregistered keys

### Requirement: A resolver serves only its own environment
Each environment MUST run its own resolver, answering only from that environment's records. A username belonging to a deployment in one environment MUST NOT resolve at another environment's edge.

This MUST NOT replace the network-layer enforcement of environment separation, which remains the guarantee; it removes the case where an edge could route to the wrong environment at all.

#### Scenario: A username does not resolve in the wrong environment
- **WHEN** a client presents a production deployment's username to the development edge
- **THEN** it does not resolve, and the connection is refused

#### Scenario: Network-layer separation is unaffected
- **WHEN** environment separation is verified
- **THEN** each environment's tenant network policy still admits only that environment's edge
