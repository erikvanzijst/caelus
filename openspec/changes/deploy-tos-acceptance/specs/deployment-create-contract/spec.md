## ADDED Requirements

### Requirement: Deployment create requires an accepted ToS version

The deployment create input MUST include a required `tos_version` field for both
REST API `POST /deployments` and the equivalent CLI create command. The value
MUST be a well-formed ISO-8601 date (`YYYY-MM-DD`); the API does not validate it
against any server-side "current" version. A create request without a
well-formed `tos_version` MUST be rejected with a client validation error and
MUST NOT create a deployment.

#### Scenario: Valid create request includes the ToS version

- **WHEN** a client sends a `POST /deployments` request whose body includes
  `tos_version` `2026-07-01` along with the other supported fields
- **THEN** the API accepts the request and processes deployment creation

#### Scenario: Create payload omits the ToS version

- **WHEN** a client sends a `POST /deployments` request with no `tos_version`
- **THEN** the API rejects the request with a client validation error and no
  deployment is created

#### Scenario: Create payload has a malformed ToS version

- **WHEN** a client sends a `POST /deployments` request whose `tos_version` is
  not a `YYYY-MM-DD` date
- **THEN** the API rejects the request with a client validation error and no
  deployment is created

#### Scenario: CLI create input requires the ToS version

- **WHEN** a user runs the CLI create-deployment command without the
  `--tos-version` option
- **THEN** the CLI rejects the input and does not invoke deployment creation
