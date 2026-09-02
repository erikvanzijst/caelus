## Purpose

A client that connects to the SSH edge for the first time must decide whether
to trust whatever answers, and the platform already knows the correct host key
without saying it. This capability publishes that key -- together with the
edge's address -- on a dedicated endpoint, so a client can verify the endpoint
it is connecting to instead of trusting it on sight.

## ADDED Requirements

### Requirement: A dedicated endpoint publishes the edge's address and host key
The platform MUST expose a read endpoint (`GET /api/ssh`) returning, for the
environment, the SSH edge's user-facing host and port and the public half of
the edge's host key. The host key MUST be keyed by its OpenSSH key type, so a
client selects the type it supports and pins the matching value.

The endpoint MUST be publicly readable, requiring no authentication. The
response is public key material that confers nothing on its holder, and the
edge presents the same key to every client during the handshake, so gating it
behind a session protects nothing.

The endpoint MUST NOT be gated on any particular deployment's product or
state. The host key is a per-environment fact, and a client needs it before it
knows which deployment to address; tying its availability to a deployment's
chart would make it un-fetchable precisely for the deployments that differ
from the check's assumptions.

#### Scenario: The edge's details are published
- **WHEN** any caller requests the SSH edge details
- **THEN** the response includes the environment's edge host, port, and host public key

#### Scenario: No session is required
- **WHEN** a caller requests the SSH edge details without an authenticated identity
- **THEN** the response is served, not refused

#### Scenario: Availability is independent of any deployment
- **WHEN** the SSH edge details are requested
- **THEN** the response is the same regardless of any particular deployment's product or state

### Requirement: The published key is the one the edge presents
The host key the endpoint returns MUST come from platform configuration and
MUST be the same key the edge actually presents to clients. Each environment
MUST publish the key of its own edge.

A client that connects to the edge MUST be able to compare the key it is
offered against the published value and find them equal.

#### Scenario: The published key is the one presented
- **WHEN** a client connects to the edge and compares its host key against the published value
- **THEN** they match

#### Scenario: Environments publish their own key
- **WHEN** the endpoint is requested against different environments
- **THEN** each reports the host key of its own edge

### Requirement: An unconfigured key is reported as absent, never as trustable
When the environment has not configured a host key, the endpoint MUST report
an empty host key rather than omitting the field or fabricating a value. A
client MUST treat an empty host key as "cannot verify" and refuse to connect,
never as permission to trust the first answer.

#### Scenario: Unconfigured environment reports an empty key
- **WHEN** the environment has not configured a host key
- **THEN** the response reports an empty host key

#### Scenario: A client refuses rather than trusts
- **WHEN** a client finds the published host key empty
- **THEN** it refuses to connect rather than accepting the edge's key on first use
