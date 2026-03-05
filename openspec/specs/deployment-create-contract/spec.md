# deployment-create-contract Specification

## Purpose
TBD - created by archiving change drop-deployment-domainname. Update Purpose after archive.
## Requirements
### Requirement: Deployment write contracts exclude domainname across API and CLI
The system MUST define deployment write inputs without a top-level `domainname` field for REST API `POST /deployments`, REST API `PUT /deployments`, and equivalent CLI create/update commands.

#### Scenario: Valid create request without domainname
- **WHEN** a client sends a `POST /deployments` request containing only supported fields
- **THEN** the API accepts the request and processes deployment creation

#### Scenario: Create payload includes removed domainname field
- **WHEN** a client sends a `POST /deployments` request containing `domainname`
- **THEN** the API rejects the request with a client validation error indicating unsupported input

#### Scenario: Update payload includes removed domainname field
- **WHEN** a client sends a `PUT /deployments` request containing `domainname`
- **THEN** the API rejects the request with a client validation error indicating unsupported input

#### Scenario: CLI create input includes removed domainname field
- **WHEN** a user runs the CLI create-deployment command with a `domainname` option/argument
- **THEN** the CLI rejects the input and does not invoke deployment creation

#### Scenario: CLI update input includes removed domainname field
- **WHEN** a user runs the CLI update-deployment command with a `domainname` option/argument
- **THEN** the CLI rejects the input and does not invoke deployment update

### Requirement: Deployment reads continue returning domainname
The system MUST continue to include `domainname` in deployment read responses, including `GET /deployment` responses, after the write-contract change.

#### Scenario: Read deployment after create/update contract change
- **WHEN** a client retrieves a deployment using the read endpoint
- **THEN** the response still includes the `domainname` field

### Requirement: Create service derives persisted domainname from template schema and user values
During create-deployment and update-deployment, the service MUST derive `DeploymentORM.domainname` from `user_values_json` using the schema from `desired_template`.

#### Scenario: Template schema contains a domainname-titled field
- **WHEN** the desired template schema contains one or more fields anywhere in the schema document whose `title` matches `domainname` case-insensitively
- **THEN** the service selects the first matching field and persists `DeploymentORM.domainname` from the corresponding `user_values_json` value

#### Scenario: Template schema has no domainname-titled field
- **WHEN** the desired template schema contains no field whose `title` equals `domainname`
- **THEN** the service persists `DeploymentORM.domainname` as `null`

#### Scenario: Update re-derives persisted domainname
- **WHEN** a client updates a deployment with new `user_values_json`
- **THEN** the service re-derives and persists `DeploymentORM.domainname` using the same recursive first-match rule

### Requirement: Dashboard deployment form removes dedicated Domain name field
The UI Dashboard MUST not render a dedicated `Domain name` TextField and MUST not include a top-level `domainname` in deployment write payloads.

#### Scenario: User submits deployment form
- **WHEN** the user completes and submits the deployment create form
- **THEN** the generated request payload excludes `domainname`

#### Scenario: UI request mapping for deployment creation
- **WHEN** form values are transformed into an API create request
- **THEN** no mapper or client type adds `domainname` to the outgoing payload

