# Implementation Contracts (Issue 001)

Date: 2026-02-14

## V1 Platform Constraints

1. Templates are Helm-only (`package_type = helm-chart`).
2. Caelus DB is the source of truth.
3. Worker runtime is a separate deployment from API, using the same codebase.
4. Queue is DB-backed; Postgres uses `FOR UPDATE SKIP LOCKED`.
5. User-editable values are only under `values.user.*`.
6. `values_schema_json.properties.user` is optional.
7. Upgrades are admin-only in V1 (`user.is_admin`).
8. Deletion is hard-delete of Kubernetes resources for the instance lifecycle.

## Naming Contract

`deployment_uid` format:

`{product_slug}-{user_slug}-{suffix6}`

Where:

1. `product_slug` and `user_slug` are lowercase slug tokens (`[a-z0-9-]`).
2. `suffix6` matches `[0-9a-z]{6}`.
3. Final value must be a valid DNS label and length <= 63.
4. Base is truncated to 56 chars to reserve `-suffix6`.
5. If base is empty after slug/trim, fallback base is `dep`.

V1 identity mapping:

1. `namespace_name = deployment_uid`
2. `release_name = deployment_uid`

## Reconcile Vocabulary

Deployment statuses:

- `pending`
- `provisioning`
- `ready`
- `upgrading`
- `deleting`
- `deleted`
- `error`

Job statuses:

- `queued`
- `running`
- `done`
- `failed`

Job reasons:

- `create`
- `update`
- `delete`
- `drift`
