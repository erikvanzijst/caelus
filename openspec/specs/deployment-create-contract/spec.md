# deployment-create-contract Specification

## Purpose
TBD - created by archiving change drop-deployment-domainname. Update Purpose after archive.
## Requirements
### Requirement: Deployment write contracts exclude hostname across API and CLI
The system MUST define deployment write inputs without a top-level `hostname` field for REST API `POST /deployments`, REST API `PUT /deployments`, and equivalent CLI create/update commands.

#### Scenario: Valid create request without hostname
- **WHEN** a client sends a `POST /deployments` request containing only supported fields
- **THEN** the API accepts the request and processes deployment creation

#### Scenario: Create payload includes hostname field
- **WHEN** a client sends a `POST /deployments` request containing `hostname`
- **THEN** the API rejects the request with a client validation error indicating unsupported input

#### Scenario: Update payload includes hostname field
- **WHEN** a client sends a `PUT /deployments` request containing `hostname`
- **THEN** the API rejects the request with a client validation error indicating unsupported input

#### Scenario: CLI create input includes hostname field
- **WHEN** a user runs the CLI create-deployment command with a `hostname` option/argument
- **THEN** the CLI rejects the input and does not invoke deployment creation

#### Scenario: CLI update input includes hostname field
- **WHEN** a user runs the CLI update-deployment command with a `hostname` option/argument
- **THEN** the CLI rejects the input and does not invoke deployment update

### Requirement: Deployment reads return hostname
The system MUST include `hostname` (renamed from `domainname`) in deployment read responses, including `GET /deployment` responses.

#### Scenario: Read deployment returns hostname field
- **WHEN** a client retrieves a deployment using the read endpoint
- **THEN** the response includes the `hostname` field (not `domainname`)

### Requirement: Deployment reads return name and namespace
The system MUST include `name` and `namespace` in deployment read responses. The field `deployment_uid` MUST NOT appear in API responses.

#### Scenario: Read deployment returns name and namespace fields
- **WHEN** a client retrieves a deployment using the read endpoint
- **THEN** the response includes the `name` field and the `namespace` field
- **AND** the response does NOT include a `deployment_uid` field

### Requirement: Create and update services derive hostname from template schema and user values
During create-deployment and update-deployment, the service MUST derive `DeploymentORM.hostname` from `user_values_json` using the schema from `desired_template`. The schema field is identified by `title` matching `hostname` (case-insensitive).

Additionally, the create-deployment service MUST generate and persist both `DeploymentORM.name` (Helm release name) and `DeploymentORM.namespace` (Kubernetes namespace) at creation time, using the naming functions defined in the `deployment-naming` and `deployment-namespace` capabilities.

#### Scenario: Template schema contains a hostname-titled field
- **WHEN** the desired template schema contains one or more fields anywhere in the schema document whose `title` matches `hostname` case-insensitively
- **THEN** the service selects the first matching field and persists `DeploymentORM.hostname` from the corresponding `user_values_json` value

#### Scenario: Template schema has no hostname-titled field
- **WHEN** the desired template schema contains no field whose `title` equals `hostname`
- **THEN** the service persists `DeploymentORM.hostname` as `null`

#### Scenario: Update re-derives hostname
- **WHEN** a client updates a deployment with new `user_values_json`
- **THEN** the service re-derives and persists `DeploymentORM.hostname` using the same recursive first-match rule

#### Scenario: Deployment creation generates name and namespace
- **WHEN** a new deployment is created
- **THEN** the service generates `name` using `generate_deployment_name(product_name)` and `namespace` using `generate_deployment_namespace(user_email)`
- **AND** both values are persisted to the deployment record before flushing

### Requirement: Create and update services validate hostname before persisting
During create-deployment and update-deployment, after deriving the hostname, the service MUST call `require_valid_hostname_for_deployment()` to validate the hostname before flushing to the database. If validation fails, the service MUST raise an appropriate exception and not persist the deployment.

#### Scenario: Deployment creation with invalid hostname
- **WHEN** a client creates a deployment whose derived hostname fails validation (e.g., reserved, in use, not resolving)
- **THEN** the API returns an error response and the deployment is not created

#### Scenario: Deployment update with invalid hostname
- **WHEN** a client updates a deployment and the new derived hostname fails validation
- **THEN** the API returns an error response and the deployment is not updated

#### Scenario: Deployment with no hostname field skips validation
- **WHEN** a deployment is created or updated and the derived hostname is `null`
- **THEN** hostname validation is skipped and the deployment proceeds normally

### Requirement: Dashboard deployment form removes dedicated Domain name field
The UI Dashboard MUST not render a dedicated `Domain name` TextField and MUST not include a top-level `hostname` (formerly `domainname`) in deployment write payloads.

#### Scenario: User submits deployment form
- **WHEN** the user completes and submits the deployment create form
- **THEN** the generated request payload excludes `hostname`

## Requirements from edit-deployment-config

### Requirement: Update payload allows same template version

#### Scenario: Update payload allows same template version
- **WHEN** a client sends a `PUT /deployments` request with `desired_template_id` equal to the current value
- **THEN** the API accepts the request (previously rejected with "Can only upgrade to newer versions")
