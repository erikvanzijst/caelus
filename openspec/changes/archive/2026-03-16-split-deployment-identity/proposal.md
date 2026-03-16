## Why

The current `deployment_uid` field on `DeploymentORM` serves as both the Helm release name and Kubernetes namespace. Because it encodes both the product name and user email into a single slug (`{product_slug}-{user_slug}-{suffix6}`), it can approach the 63-character DNS label limit — especially after Kubernetes appends controller-revision-hashes and chart resource suffixes. Splitting into two purpose-specific identifiers gives each field a tighter length budget and clearer semantics.

## What Changes

- **BREAKING**: Rename `DeploymentORM.deployment_uid` column to `name` (used as Helm release name)
- Add new `DeploymentORM.namespace` column (used as Kubernetes namespace)
- Change name generation: `"{slugify(product_name)[:20]}-{random6}"` (max 27 chars)
- New namespace generation: `"{slugify(email)[:20]}-{random9}"` (max 30 chars)
- `_resolve_identity()` returns `(deployment.name, deployment.namespace)` instead of `(uid, uid)`
- Alembic migration renames column, adds `namespace` seeded from old `deployment_uid` values
- All code, tests, API schemas, and TypeScript types updated to use `name` instead of `deployment_uid`

## Capabilities

### New Capabilities
- `deployment-namespace`: Generation, storage, and usage of the deployment namespace identifier — separate from the release name
- `deployment-naming`: Generation of the Helm release name (`name` field) and namespace, replacing the single `deployment_uid`

### Modified Capabilities
- `deployment-create-contract`: Deployment creation now generates and persists both `name` and `namespace` instead of a single `deployment_uid`

## Impact

- **Database**: Column rename (`deployment_uid` → `name`), new `namespace` column, index updates
- **API responses**: `deployment_uid` field replaced by `name` and `namespace` in `DeploymentRead`
- **UI**: TypeScript `Deployment` interface updated — `deployment_uid` → `name` + `namespace`
- **Reconciler**: `_resolve_identity()` and `_validate_input_state()` updated
- **Naming service**: `generate_deployment_uid()` replaced by `generate_deployment_name()` and `generate_deployment_namespace()`
- **Tests**: All references to `deployment_uid` updated across test files
