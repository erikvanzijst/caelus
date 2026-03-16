## MODIFIED Requirements

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

### Requirement: Deployment reads return name and namespace
The system MUST include `name` and `namespace` in deployment read responses. The field `deployment_uid` MUST NOT appear in API responses.

#### Scenario: Read deployment returns name and namespace fields
- **WHEN** a client retrieves a deployment using the read endpoint
- **THEN** the response includes the `name` field and the `namespace` field
- **AND** the response does NOT include a `deployment_uid` field
