## ADDED Requirements

### Requirement: Deployment namespace generation
The system MUST generate a namespace identifier for each new deployment using the formula `"{slugify(email)[:20]}-{random9}"`, where `slugify` lowercases, replaces non-alphanumeric characters with hyphens, collapses consecutive hyphens, and strips leading/trailing hyphens. The truncation to 20 characters MUST strip any resulting trailing hyphens. The random suffix MUST be 9 base36 characters (`[0-9a-z]{9}`).

#### Scenario: Namespace generated from normal email
- **WHEN** a deployment is created for a user with email `alice.smith@example.com`
- **THEN** the namespace starts with a slugified prefix of the email (e.g., `alice-smith-example-`) followed by a 9-character random suffix
- **AND** the total namespace length MUST NOT exceed 30 characters

#### Scenario: Namespace generated from long email
- **WHEN** a deployment is created for a user with a very long email address
- **THEN** the email slug is truncated to at most 20 characters before appending the random suffix
- **AND** the truncation MUST NOT leave a trailing hyphen

#### Scenario: Namespace generated from email with special characters
- **WHEN** a deployment is created for a user with email containing `+`, `.`, `@`, or other non-alphanumeric characters
- **THEN** all non-alphanumeric characters are replaced with hyphens, consecutive hyphens are collapsed, and leading/trailing hyphens are stripped before truncation

#### Scenario: Generated namespace is a valid DNS label
- **WHEN** any namespace is generated
- **THEN** it MUST be a valid DNS label: lowercase alphanumeric and hyphens only, starting and ending with an alphanumeric character, at most 63 characters

### Requirement: Deployment namespace is persisted and immutable
The system MUST store the generated namespace in the `namespace` column of the `deployment` table. The namespace MUST be set at deployment creation time and MUST NOT be modified after creation.

#### Scenario: Namespace persisted on create
- **WHEN** a new deployment is created
- **THEN** the `namespace` column is populated with the generated namespace value

#### Scenario: Namespace not modified on update
- **WHEN** a deployment is updated (e.g., template change, user values change)
- **THEN** the `namespace` column value MUST remain unchanged

### Requirement: Namespace used as Kubernetes namespace
The reconciler MUST use the deployment's `namespace` field as the Kubernetes namespace when provisioning, updating, or deleting the deployment's Helm release.

#### Scenario: Reconciler uses namespace for helm install
- **WHEN** the reconciler applies a deployment
- **THEN** it calls `ensure_namespace(name=deployment.namespace)` and passes `namespace=deployment.namespace` to `helm_upgrade_install`

#### Scenario: Reconciler uses namespace for helm uninstall
- **WHEN** the reconciler deletes a deployment
- **THEN** it passes `namespace=deployment.namespace` to `helm_uninstall` and calls `delete_namespace(name=deployment.namespace)`

### Requirement: Existing deployments seeded with namespace from deployment_uid
The database migration MUST populate the `namespace` column for all existing deployment rows using the current `deployment_uid` value (which was previously used as the namespace in Kubernetes).

#### Scenario: Migration seeds existing rows
- **WHEN** the migration runs on a database with existing deployments
- **THEN** every existing deployment row has its `namespace` column set to its pre-existing `deployment_uid` value
- **AND** the `namespace` column is NOT NULL after the migration completes
