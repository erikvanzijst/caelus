## ADDED Requirements

### Requirement: The upstream address convention is a contract shared with the charts
The resolver derives a deployment's upstream address from the deployment's own identity by a fixed naming convention rather than from a stored value. That convention MUST be the same one every product chart uses to name the Service fronting its sidecar, and MUST be documented on both sides as shared rather than as an internal detail of either.

Neither side may change it alone. The coupling is invisible in both directions — the resolver names a Service it never validates, and a chart names a Service nothing in its own release consults — so a unilateral change produces deployments that authenticate successfully and then connect to nothing, with the failure appearing at the edge rather than where the change was made.

The port the resolver dials MUST likewise be the single platform sidecar port that every profile listens on, so that a deployment's profile has no bearing on how the edge addresses it.

#### Scenario: Convention matches on both sides
- **WHEN** a deployment is rendered and a client connects to it
- **THEN** the address the resolver returns names the Service that deployment's chart rendered

#### Scenario: The convention is documented as shared
- **WHEN** the naming convention is documented
- **THEN** both the resolver's documentation and the chart's state that it is shared and cannot be changed on one side alone

#### Scenario: Profiles do not change how the edge addresses a deployment
- **WHEN** deployments running different access profiles are resolved
- **THEN** the resolver derives each upstream address the same way, without knowing which profile the deployment runs

#### Scenario: A deployment renaming its Service becomes unreachable
- **WHEN** a chart renders a Service whose name does not follow the shared convention
- **THEN** connections to that deployment resolve and then fail to reach it, rather than being refused at authentication
